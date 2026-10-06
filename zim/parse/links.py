# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import re
import os

from zim.parse.encode import url_encode
from zim.parse.encode import url_decode

# Some often used regexes
is_uri_re = re.compile(r'^(\w[\w\+\-\.]*):')
	# "scheme:"
is_url_re = re.compile(r'^(\w[\w\+\-\.]*)://')
	# "scheme://"
is_www_link_re = re.compile(r'^www\.([\w\-]+\.)+[\w\-]+')
	# "www." followed by 2 or more domain sections
	# See also 'url_re' in 'formats/wiki.py' following the GFM scheme
is_email_re = re.compile(r'^(mailto:\S+|[^\s:]+)\@\S+\.\w+(\?.+)?$', re.U)
	# "mailto:" address
	# name "@" host
	# but exclude other uris like mid: and cid:
is_path_re = re.compile(r'^(/|\.\.?[/\\]|~.*[/\\]|[A-Za-z]:\\)')
	# / ~/ ./ ../ ~user/  .\ ..\ ~\ ~user\
	# X:\
is_win32_path_re = re.compile(r'^[A-Za-z]:[\\/]')
	# X:\ (or X:/)
is_win32_share_re = re.compile(r'^(\\\\[^\\]+\\.+|smb://)')
	# \\host\share
	# smb://host/share
is_interwiki_re = re.compile(r'^(\w[\w\+\-\.]*)\?(.*)', re.U)
	# identifier "?" path
is_interwiki_keyword_re = re.compile(r'^\w[\w+\-.]*$', re.U)


def uri_scheme(link):
	'''Function that returns a scheme for URIs, URLs and email addresses'''
	if is_email_re.match(link):
		return 'mailto'
	else:
		m = is_uri_re.match(link)
		if m:
			# Includes URLs, but also URIs like "mid:", "cid:"
			return m.group(1)
		else:
			return None


def normalize_win32_share(path):
	r'''Translates paths for windows shares in the platform specific
	form. So on windows it translates C{smb://} URLs to C{\\host\share}
	form, and vice versa on all other platforms.
	Just returns the original path if it was already in the right form,
	or when it is not a path for a share drive.
	@param path: a filesystem path or URL
	@returns: the platform specific path or the original input path
	'''
	if os.name == 'nt':
		if path.startswith('smb://'):
			# smb://host/share/.. -> \\host\share\..
			path = path[4:].replace('/', '\\')
			path = url_decode(path)
	else:
		if path.startswith('\\\\'):
			# \\host\share\.. -> smb://host/share/..
			path = 'smb:' + url_encode(path.replace('\\', '/'))

	return path


def link_type(link):
	'''Function that returns a link type for urls and page links'''
	# More strict than uri_scheme() because page links conflict with
	# URIs without "//" or without "@"
	m_url = is_url_re.match(link)
	if m_url:
		if link.startswith('zim+'):
			type = 'notebook'
		else:
			type = m_url.group(1)
	elif link.startswith('file:/'):
		type = 'file' # special case with single "/" not matched as URL
	elif is_email_re.match(link):
		type = 'mailto'
	elif is_www_link_re.match(link):
		type = 'http'
	elif '@' in link and (
		link.startswith('mid:') or
		link.startswith('cid:')
	):
		return link[:3]
		# email message uris, see RFC 2392
	elif is_win32_share_re.match(link):
		type = 'smb'
	elif is_path_re.match(link):
		type = 'file'
	elif is_interwiki_re.match(link):
		type = 'interwiki'
	else:
		type = 'page'
	return type


def is_wiki_link(link: str) -> bool:
	'''Check whether this is an wiki link or not
	usefull to distinguish between internal and external links
	key is whether other applications will be able to resolve the link or not
	'''
	# NOTE: attachments are not considered wiki links even though resolving
	#       them depends on the notebook layout - could be fixed by making
	#       them more explicit internal - e.g. "page:/file.pdf"
	return link_type(link) in ('page', 'interwiki')


# ## URL link Parsing ##
#
# NOTE: we follow rules of GFM spec, except:
#  - we allow any URL scheme
#  - we allow only one domain section (e.g. "localhost")
#  - we add a file URI match
#  - do not allow to start with "__" because of conflict with mark markup parsing
# For GFM Markdown parser, remove these exceptions
#
# File paths cannot contain '\', '/', ':', '*', '?', '"', '<', '>', '|'
# These are valid URL / path seperators: / \ : ? |
# So restrict matching " < > and also '
_url = r'''
	(www\.|https?://|\w+://)			# autolink & autourl prefix
	(?P<domain>([\w\-]+\.)*[\w\-]+)		# domain sections (GFM says "2 or more", so "+" instead of "*")
	[^\s<]*								# any non-space char except "<"
	'''
_email = r'''
	(mailto:)?
	[\w\.\-_+]+@						# email prefix
	([\w\-_]+\.)+[\w\-_]+				# email domain
	'''
_file = r'''
	file:/+
	[^\s"<>\']+
	'''

url_link_re = re.compile(
	'''\\b
	(?!__)(?P<url>%s)     |
	(?!__)(?P<email>%s) |
	(?P<fileuri>%s)
	''' % (_url, _email, _file),
	re.VERBOSE
)


url_link_trailing_punctuation = ('?', '!', '.', ',', ':', '*', '_', '~', "'", '"')


def match_url_link(text):
	'''Match regex and count number of closing brackets
	See L{https://github.github.com/gfm/#autolinks-extension-}
	@param text: text to match as url
	@returns: the url or None
	'''
	m = url_link_re.match(text)
	if m:
		url = m.group(0)
		if m.lastgroup == 'email':
			# Do not allow end in "-" or "_", use trailing "."
			# modified rule from GFM to allow trailing __ because of mark markup
			while url:
				if url[-1] == '.':
					url = url[:-1]
				elif url[-1] == '_' and url[-2] == '_':
					url = url[:-2]
				elif url[-1] in ('-', '_'):
					return None
				else:
					break
			return url or None

		# continue processing regular URL or file URI
		if m.lastgroup == 'url':
			domain = m.group('domain').split('.')
			if '_' in domain[-1] or (len(domain) > 1 and '_' in domain[-2]):
				# Last two domain sections cannot contain "_"
				return None
	else:
		return None

	while url:
		if url[-1] in url_link_trailing_punctuation \
			or (url[-1] == ')' and url.count(')') > url.count('(')):
				url = url[:-1]
		elif url[-1] == ';':
			m = re.search(r'&\w+;$', url)
			if m:
				ref = m.group(0)
				url = url[:-len(ref)]
			else:
				url = url[:-1]
		else:
			return url
	else:
		return None


def is_url_link(text):
	'''Matches url_re and number of closing brackets matches
	See L{https://github.github.com/gfm/#autolinks-extension-}
	@param text: text to match as url
	@returns: C{True} if C{text} is a valid url according to GFM rules
	'''
	url = match_url_link(text)
	return url == text # No trailing puntuation or ")" excluded
	# do not add ";" here, it is handled separatedly in the function


# Old regex which was used before adopting the GFM logic for closing brackets etc.
_classes = {'c': r'[^\s"<>\']'} # limit the character class a bit
old_url_link_re = re.compile(r'''(
	\b \w[\w\+\-\.]+:// %(c)s* \[ %(c)s+ \] (?: %(c)s+ [\w/] )?  |
	\b \w[\w\+\-\.]+:// %(c)s+ [\w/]                             |
	\b mailto: %(c)s+ \@ %(c)s* \[ %(c)s+ \] (?: %(c)s+ [\w/] )? |
	\b mailto: %(c)s+ \@ %(c)s+ [\w/]                            |
	\b %(c)s+ \@ %(c)s+ \. \w+ \b
)''' % _classes, re.X | re.U)
	# Full url regex - much more strict then the is_url_re
	# The host name in an uri can be "[hex:hex:..]" for ipv6
	# but we do not want to match "[http://foo.org]"
	# See rfc/3986 for the official -but unpractical- regex
