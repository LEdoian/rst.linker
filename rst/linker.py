"""
Sphinx plugin to add links and timestamps to the changelog.
"""

import re
import os
import operator
import subprocess

import six


class Repl:
    @classmethod
    def from_defn(cls, defn):
        "Return the first Repl subclass that works with this"
        instances = (subcl(defn) for subcl in cls.__subclasses())
        return next(filter(None, instances))

    def __init__(self, defn):
        vars(self).update(defn)

    def matches(self, text):
        return re.match(self.pattern+'$', text)

    def __bool__(self):
        return False


class URLLinker(Repl):
    """
    Each replacement should have the form:

    {
        pattern: "Issue #?(?P<number>\d+)",
        url: "{bitbucket}/jaraco/rst.linker/issues/{number}",
        bitbucket: https://bitbucket.org
    }

    Currently, each named group must be unique across all Repl objects used
    in a replacement.
    """
    def replace(self, match, replacer_vars):
        text = match.group(0)
        ns = match.groupdict()
        ns.update(vars(self))
        ns.update(replacer_vars)
        hyperlink = '`{text} <{href}>`_'
        return hyperlink.format(text=text, href=self.url.format(**ns))

    def __bool__(self):
        return 'url' in vars(self)


class SCMTimestamp(Repl):
    """
    Replace content with a version number to include the date stamp
    from the SCM.

    For example, consider a changelog with the following:

        1.0
        ---

        Changed something.

    The following replacement definition would add a datestamp
    after the heading:

    {
        pattern: r"^((?P<scm_version>\d+(\.\d+){1,2})\n-+\n)",
        with_scm: "{text}\nTagged {rev[timestamp]}\n",
    }

    If the scm_version is detected, a timestamp will be added to the
    namespace.
    """
    def replace(self, match, replacer_vars):
        text = match.group(0)
        scm_version = match.group('scm_version')
        rev = self._get_scm_info_for(scm_version)
        if not rev:
            return text
        ns = match.groupdict()
        ns.update(vars(self))
        ns.update(replacer_vars)
        return self.with_scm.format(**ns)

    @staticmethod
    def _get_scm_info_for(scm_version):
        cmd = ['git', 'log', '-1', '--format=%ai', scm_version]
        try:
            ts = subprocess.check_output(cmd).decode('utf-8').strip()
        except Exception:
            return
        return dict(timestamp=ts)

    def __bool__(self):
        return 'with_scm' in vars(self)


class Replacer(list):
    @staticmethod
    def load(filename):
        defn = dict()
        with open(filename) as stream:
            six.exec_(stream.read(), defn)
        return defn

    @classmethod
    def from_definition(cls, defn):
        """
        A definition may contain the following members:

        - using: a dictionary of variables available for substitution
        - replace: a list of replacement definitions.
        """
        repls = map(Repl.from_defn, defn.get('replace', []))
        self = cls(repls)
        vars(self).update(defn.get('using', {}))
        return self

    def run(self, source):
        by_pattern = operator.attrgetter('pattern')
        pattern = '|'.join(map(by_pattern, self))
        return re.sub(pattern, self.replace, source)

    def replace(self, match):
        text = match.group(0)
        # determine which replacement matched
        repl = next(repl for repl in self if repl.matches(text))
        return repl.replace(match, vars(self))

    def write_links(self, source, target):
        with open(source) as source:
            out = self.run(source.read())
        with open(target, 'w') as dest:
            dest.write(out)


def setup(app):
    app.add_config_value('link_files', {}, '')
    app.connect('builder-inited', make_links)

def _extend_name(filename):
    base, ext = os.path.splitext(filename)
    return base + ' (links)' + ext

def make_links(app):
    files_def = app.config.link_files
    for filename, defn in files_def.items():
        replacer = Replacer.from_definition(defn)
        target = _extend_name(filename)
        replacer.write_links(filename, target)
    app.connect('build-finished', remove_targets)

def remove_targets(app, exception):
    files_def = app.config.link_files
    for filename in files_def:
        target = _extend_name(filename)
        os.remove(target)