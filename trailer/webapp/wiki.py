'''
Created on 04.04.2016

@author: kraft-p
'''

import markdown
import cherrypy
import os
from cherrypy import expose
from pathlib import Path

from . import mime, mimetype
from .. import home

postonly = cherrypy.tools.allow(methods=['POST'])  # @UndefinedVariable

webdir = home / 'web'
wikihome = webdir / 'wiki'


class PatternLink(markdown.inlinepatterns.Pattern):
    """
    Creates a link from a specific Regular Expression pattern
    """

    def __init__(self, md, pattern, href, text, styleclass=None):
        """
        Creates the rule to substitute a pattern with a link
        md: The MarkDown object
        pattern: a regular expression of the text to be used as the pattern
        href: a substitution string to yield the linked url from the pattern. Note: Groups have one index higher as one would expect. Eg. the first group in \2
        text: a substitution string to yield the link label from the pattern. Note: Groups have one index higher as one would expect. Eg. the first group in \2
        """
        super().__init__(pattern, md)
        self.href = href
        self.text = text
        self.styleclass = styleclass

    def handleMatch(self, m):
        try:
            href = self.href(m)
        except TypeError:
            href = m.expand(self.href)
        try:
            text = self.text(m)
        except TypeError:
            text = m.expand(self.text)
        el = markdown.util.etree.Element("a")
        el.set('href', href)
        if self.styleclass:
            el.set('class', self.styleclass)
        el.text = markdown.util.AtomicString(text)
        return el


class TagPattern(markdown.inlinepatterns.Pattern):
    """
    Creates a link from a specific Regular Expression pattern
    """

    def __init__(self, md, pattern, tag, text='', **kwargs):
        """
        Creates the rule to substitute a pattern with a link
        md: The MarkDown object
        pattern: a regular expression of the text to be used as the pattern
        href: a substitution string to yield the linked url from the pattern. Note: Groups have one index higher as one would expect. Eg. the first group in \2
        text: a substitution string to yield the link label from the pattern. Note: Groups have one index higher as one would expect. Eg. the first group in \2
        """
        super().__init__(pattern, md)
        self.tag = tag
        self.text = text
        self.attr = kwargs

    def handleMatch(self, m):
        try:
            text = self.text(m)
        except TypeError:
            text = m.expand(self.text)

        el = markdown.util.etree.Element(self.tag)
        for k, v in self.attr.items():
            el.set(k.lstrip('_'), m.expand(v))

        el.text = markdown.util.AtomicString(text)
        return el


class SymbolPattern(markdown.inlinepatterns.Pattern):
    def __init__(self, md, pattern, out):
        super(SymbolPattern, self).__init__(pattern, md)
        self.out = out

    def handleMatch(self, m):
        return self.out


# The UrlizePattern class is taken from: https://github.com/r0wb0t/markdown-urlize/blob/master/urlize.py
# Global Vars
URLIZE_RE = '(%s)' % '|'.join([
    r'<(?:f|ht)tps?://[^>]*>',
    r'\b(?:f|ht)tps?://[^)<>\s]+[^.,)<>\s]',
    r'\bwww\.[^)<>\s]+[^.,)<>\s]',
    r'[^(<\s]+\.(?:com|net|org|de)\b',
])


class UrlizePattern(markdown.inlinepatterns.Pattern):
    """ Return a link Element given an autolink (`http://example/com`). """

    def handleMatch(self, m):
        url = m.group(2)

        if url.startswith('<'):
            url = url[1:-1]

        text = url

        if not url.split('://')[0] in ('http', 'https', 'ftp'):
            if '@' in url and not '/' in url:
                url = 'mailto:' + url
            else:
                url = 'http://' + url

        el = markdown.util.etree.Element("a")
        el.set('href', url)
        el.text = markdown.util.AtomicString(text)
        return el


class TrailerExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        """ Replace autolink with UrlizePattern """
        md.inlinePatterns['link log'] = PatternLink(md, '(log:)([0-9]+)', r'/log/\3', u'\u25B8' + r'\2\3')
        md.inlinePatterns['link wiki'] = PatternLink(md, '(wiki:)([\w/.-]+)', r'/wiki/\3', u'[\\3]')
        md.inlinePatterns['link svn'] = PatternLink(md, '(svn:)([\w/]+)', r'/snvlog/\3', u'[\\3]')
        md.inlinePatterns['replace rarrow'] = SymbolPattern(md, r'(-->)', '\u2192')
        md.inlinePatterns['replace larrow'] = SymbolPattern(md, r'(<--)', '\u2190')
        md.inlinePatterns['replace rarrow big'] = SymbolPattern(md, r'(==>)', '\u21D2')
        md.inlinePatterns['replace larrow big'] = SymbolPattern(md, r'(<==)', '\u21D0')
        md.inlinePatterns['home button'] = PatternLink(md, r'(/HOME)', '/', '\u2302', 'button')

        md.inlinePatterns['strikethrough'] = TagPattern(
            md, r'(done:)(.+)', 'span', '\u2714\\3', _class="active")
        md.inlinePatterns['warning'] = TagPattern(
            md, r'(!!)(.+)', 'span', '\\3', _class='warning')
        md.inlinePatterns['image'] = TagPattern(
            md, r'(image:)([\w/.]+)', 'img', '', src=r'/img/\3')
        md.inlinePatterns['question'] = TagPattern(
            md, r'(\?\?)(.+)', 'span', '\u2753\\3', _class='question')


class UrlizeExtension(markdown.Extension):
    """ Urlize Extension for Python-Markdown. """

    def extendMarkdown(self, md, md_globals):
        """ Replace autolink with UrlizePattern """
        md.inlinePatterns['autolink'] = UrlizePattern(URLIZE_RE, md)


class MarkDown:
    def __init__(self):
        te = TrailerExtension(configs={})
        al = UrlizeExtension(configs={})
        self.md = markdown.Markdown(extensions=['admonition', te, al])

    def __call__(self, s):
        return self.md.convert(s)


def remove_wiki_suffix(s):
    if s.endswith('.wiki'):
        return s[:-5]
    else:
        return s


def as_href(fn: Path):
    res = remove_wiki_suffix(fn.relative_to(webdir).as_posix())
    if not res.startswith('/'):
        res = '/' + res
    return res


class WikiPage:
    exposed = True

    def __init__(self):
        self.md = MarkDown()

    def filename(self, *args) -> Path:
        p = list(args)
        while 'wiki' in p:
            p.pop(0)
        fn = (webdir / 'wiki').joinpath(*p)
        if not fn.is_dir():
            fn = fn.with_suffix('.wiki')
        return fn.absolute()

    @expose
    @mimetype(mime.html)
    def home(self):
        return self.default()

    def to_wiki_link(self, fn: Path):
        return 'wiki:' + remove_wiki_suffix('/'.join(fn.relative_to(wikihome).parts))

    def translate(self, fn: Path, text: str):
        if fn.is_dir():
            text += '\n\nContent:\n--------\n'
            text += '\n'.join(' - ' + self.to_wiki_link(f)  # + '/' + f.name.rstrip('.wiki')
                              for f in fn.iterdir()
                              if (f.suffix == '.wiki' and 'index' not in f.name) or f.is_dir())
            text += """
                \n<a class="button" id="newfile" title="create file">+</a>
                <a class="button" id="newfolder" title="create folder">/</a>
            """
        return self.md(text)

    @expose
    @mimetype(mime.html)
    def default(self, *args):
        fn = self.filename(*args)
        template = (webdir / 'html/wiki.html').read_text(encoding='utf-8')
        if fn.exists():
            if fn.is_dir():
                try:
                    mdtext = fn.joinpath('index.wiki').read_text(encoding='utf-8')
                except FileNotFoundError:
                    mdtext = '\n# Content in ' + '/'.join(args) + '\n\n'
            else:
                mdtext = fn.read_text(encoding='utf-8')
            html = self.translate(fn, mdtext)
            return (template
                    .replace('<!--WIKI-->', html)
                    .replace('<!--SOURCE-->', mdtext))

        else:
            raise cherrypy.HTTPError(404,
                                     '{} not found in the wiki, looked at {}'
                                     .format('/'.join(args), fn.absolute()))

    @postonly
    @expose
    def save(self, href, text):
        fn = self.filename(*href.split('/'))
        if fn.is_dir():
            ifn = fn.joinpath('index.wiki')
            ifn.write_text(text, encoding='utf-8')
        else:
            fn.write_text(text, encoding='utf-8')
        return self.translate(fn, text)

    @postonly
    @expose
    def preview(self, href, text):
        fn = self.filename(*href.split('/'))
        return self.translate(fn, text)

    @postonly
    @expose
    def new(self, href: str, name: str):
        try:
            fn = self.filename(*href.split('/'))
            newfn = fn / name
            if newfn.exists():
                return self.to_wiki_link(fn / name) + ' exists already'
            if name.endswith('.wiki'):
                newfn.write_text(remove_wiki_suffix(name) + '\n==========\n')
            elif name.endswith('/'):
                newfn.mkdir()
            return as_href(newfn)
        except Exception as e:
            return str(e)

    @postonly
    @expose
    def delete(self, href: str):
        try:
            fn = self.filename(*href.split('/'))
            if fn.is_dir():
                for f in fn.iterdir():
                    f.unlink()
                fn.rmdir()
            else:
                fn.unlink()
            res = as_href(fn.parent)
            return res
        except Exception as e:
            return str(e)
