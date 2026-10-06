# Copyright 2011-2025 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.parse.searchquery import *
from zim.search import *
from zim.notebook import Path
from zim.plugins import PluginManager, indexed_fts
from zim.gui.pageview.find import FindQuery

from zim.main import SearchCommand
from tests.main import capture_stdout


# some aliases to define queries
_t = SearchQueryTerm
_any = lambda t: SearchQueryTerm('any', t)
_and = lambda *t: SearchQuery(OPERATOR_AND, t)
_or = lambda *t: SearchQuery(OPERATOR_OR, t)
_q = _and # toplevel is default an AND group


def _not(t):
	t.negate = True
	return t


class TestParseSearchQuery(tests.TestCase):

	def assertParseQuery(self, string, wanted, keywords, flags=SearchFlag(0)):
		query = parse_search_query(string, keywords, flags=flags)
		#print('==== string: %r got: "%s" wanted: "%s"' % (string, query, wanted))
		self.assertEqual(query, wanted)

		mystring = str(query)
		myquery = parse_search_query(mystring, keywords, flags=flags)
		self.assertEqual(myquery, wanted) # ensure string representation leads to same parsing result

	def testFlags(self):
		keywords = {'links'}
		string = 'foo AND NOT bar OR baz'
		wanted = _and(_any('foo'), _or(_not(_any('bar')), _any('baz')))
		wanted.flags = SEARCH_CASE_SENSITIVE|SEARCH_WHOLE_WORD
		self.assertParseQuery(string, wanted, keywords, flags=SEARCH_CASE_SENSITIVE|SEARCH_WHOLE_WORD)

	def testKeywordParsing(self):
		keywords = {'links'}
		for string, wanted in (
			('links:Foo', _q(_t('links', 'Foo'))),
			('links: Foo', _q(_t('links', 'Foo'))),
			('Links:Foo', _q(_t('links', 'Foo'))),
			('Links: Foo', _q(_t('links', 'Foo'))),
			('Links:', _q(_any('Links:'))),
				# edge case, looking for literal occurrence, not a keyword, falls back to default
			('"Links:Foo"',	_q(_any('Links:Foo'))),
				# quoted string, not a keyword, falls back to default
			('links Foo', _and(_any('links'), _any('Foo'))),
			('links=foo', _q(_t('links', 'foo', kw_operator=OPERATOR_EQUAL))),
			('links:=foo', _q(_t('links', 'foo', kw_operator=OPERATOR_EQUAL))),
			('links<foo', _q(_t('links', 'foo', kw_operator=OPERATOR_LESS_THAN))),
			('links:<foo', _q(_t('links', 'foo', kw_operator=OPERATOR_LESS_THAN))),
			('links>foo', _q(_t('links', 'foo', kw_operator=OPERATOR_GREATER_THAN))),
			('links:>foo', _q(_t('links', 'foo', kw_operator=OPERATOR_GREATER_THAN))),
			('links>=foo', _q(_t('links', 'foo', kw_operator=OPERATOR_GREATER_EQUAL))),
			('links:>=foo', _q(_t('links', 'foo', kw_operator=OPERATOR_GREATER_EQUAL))),
			('links<=foo', _q(_t('links', 'foo', kw_operator=OPERATOR_LESS_EQUAL))),
			('links:<=foo', _q(_t('links', 'foo', kw_operator=OPERATOR_LESS_EQUAL))),
		):
			self.assertParseQuery(string, wanted, keywords)

	def testImplicitKeywordMatch(self):
		keywords = {'tag': {'implicit_match': search_tag_re}}
		for string, wanted in (
			('tag:Foo', _q(_t('tag', 'Foo'))),
			('@Foo', _q(_t('tag', '@Foo'))),
			('"@Foo"', _q(_any('@Foo'))),
		):
			self.assertParseQuery(string, wanted, keywords)

	def testOperatorPrecedence(self):
		# Example from docs:
		#	Order of precedence: AND, OR, NOT
		#	so "foo AND NOT bar OR baz" means AND(foo, OR(NOT(bar), baz))
		#
		#	'foo OR bar AND dus'
		#	gives all pages that contain "dus" plus either "foo" or "bar" or both.
		#
		keywords = {'links'}
		for string, wanted in (
			('foo AND NOT bar OR baz',
				_and(_any('foo'), _or(_not(_any('bar')), _any('baz')))),
			('foo OR bar AND dus',
				_and(_or(_any('foo'), _any('bar')), _any('dus'))),
			('foo OR bar OR test AND dus', # multiple OR at the start
				_and(_or(_any('foo'), _any('bar'), _any('test')), _any('dus'))),
			('dus AND foo OR bar OR test AND dus', # multiple OR in the middle
				_and(_any('dus'), _or(_any('foo'), _any('bar'), _any('test')), _any('dus'))),
			('dus AND foo OR bar OR test', # multiple OR at the end
				_and(_any('dus'), _or(_any('foo'), _any('bar'), _any('test')))),
			('foo OR bar OR test', # only OR -> skip top-level AND group
				_or(_any('foo'), _any('bar'), _any('test'))),
		):
			self.assertParseQuery(string, wanted, keywords)

	def testNotOperator(self):
		keywords = {'links'}
		for string, wanted in (
			('NOT links: Foo', _q(_not(_t('links', 'Foo')))),
			('NOTlinks: Foo', _and(_any('NOTlinks:'), _any('Foo'))),
				# not an operator, fallback to string with default keyword
			('-links:Foo', _q(_not(_t('links', 'Foo')))),
			('- links:Foo', _q(_not(_t('links', 'Foo')))),
			('-Links:', _q(_not(_any('Links:')))),
			('-"Links:Foo"', _q(_not(_any('Links:Foo')))),
			('-links Foo', _and(_not(_any('links')), _any('Foo'))),
			('-links +Foo', _and(_not(_any('links')), _any('Foo'))),
			('NOT links Foo', _and(_not(_any('links')), _any('Foo'))),
			('links -Foo', _and(_any('links'), _not(_any('Foo')))),
			('+links -Foo', _and(_any('links'), _not(_any('Foo')))),
			('links NOT Foo', _and(_any('links'), _not(_any('Foo')))),
			('NOT links -Foo', _and(_not(_any('links')), _not(_any('Foo')))),
		):
			self.assertParseQuery(string, wanted, keywords)

	def testQuotedStrings(self):
		# Examples from docs
		keywords = {'linksto'}
		for string, wanted in (
			('"foo bar" and "+1"', _and(_any('foo bar'), _any('+1'))),
			('NOT LinksTo: ":Done"', _q(_not(_t('linksto', ':Done')))),
		):
			self.assertParseQuery(string, wanted, keywords)

	def testExplicitGrouping(self):
		keywords = {'links'}
		for string, wanted in (
			('foo OR (bar baz)', # group at end
				_or(_any('foo'), _and(_any('bar'), _any('baz')))),
			('(bar baz) OR foo', # group at start
				_or(_and(_any('bar'), _any('baz')), _any('foo'))),
			('foo OR (bar baz) OR some', # group in middle
				_or(_any('foo'), _and(_any('bar'), _any('baz')), _any('some'))),
			('(bar baz)', # only group
				_and(_any('bar'), _any('baz'))),
			('foo OR (bar (test OR TEST))', # Nested group
				_or(_any('foo'), _and(_any('bar'), _or(_any('test'), _any('TEST'))))),
			('foo OR ((test OR TEST) bar)', # Nested group
				_or(_any('foo'), _and(_or(_any('test'), _any('TEST')), _any('bar')))),
			('foo OR (bar (test OR TEST) baz)', # Nested group
				_or(_any('foo'), _and(_any('bar'), _or(_any('test'), _any('TEST')), _any('baz')))),
			('foo AND NOT bar OR baz', # Apply NOT to term
				_and(_any('foo'), _or(_not(_any('bar')), _any('baz')))),
			('foo AND NOT (bar OR baz)', # Apply NOT to group
				_and(_any('foo'), _not(_or(_any('bar'), _any('baz'))))),
			('foo AND NOT ( bar OR baz )', # with spaces
				_and(_any('foo'), _not(_or(_any('bar'), _any('baz'))))),
			('links: (bar and baz -dus)', # keyword group - no operator support except "+", "-"
				_and(_t('links', 'bar'), _t('links', 'and'), _t('links', 'baz'), _not(_t('links', 'dus')))
			)
		):
			self.assertParseQuery(string, wanted, keywords)

	def testFixingInvalidQueries(self):
		keywords = {'links'}
		for string, equivalent in (
			# groups cannot start with OR or multiple AND
			('AND +foo bar', 'foo bar'),
			('OR foo bar', 'foo bar'),
			('foo (OR bar)', 'foo (bar)'),
			# groups cannot end with AND, OR or NOT
			('foo OR', 'foo'),
			('foo AND', 'foo'),
			('foo NOT', 'foo'),
			('foo (bar NOT) baz', 'foo (bar) baz'),
			# AND and OR cannot follow another AND, OR or NOT operator
			('foo AND OR bar', 'foo OR bar'),
			('foo OR AND bar', 'foo AND bar'),
			('foo NOT AND bar', 'foo AND bar'),
			# groups cannot be empty - including toplevel - and "( )"
			('', ''),
			('    ', ''),
			('( )', ''),
			('AND', ''),
			('NOT', ''),
			# unmatched ( or )
			('(foo', 'foo'),
			('bar)', 'bar'),
			('foo (bar OR baz))', 'foo (bar OR baz)'),
			('foo (bar OR (baz)', 'foo (bar OR (baz))'),
			# more weird edge cases
			('(foo +)', 'foo'),
		):
			#print('====', string)
			with tests.LoggingFilter('zim.parsing') as warning:
				wanted = parse_search_query(equivalent, keywords)
				self.assertParseQuery(string, wanted, keywords)
				self.assertTrue(warning.captured)


class TestSearchQueryTermToRegex(tests.TestCase):

	def runTest(self):
		for value, regex, regex_word in (
			('foo', 'foo', '\\bfoo\\b'),
			('*foo', 'foo\\b', 'foo\\b'),
			('foo bar', 'foo\\W+bar', '\\bfoo\\W+bar\\b'),
			('foo*bar', '\\bfoo\\S*bar\\b', '\\bfoo\\S*bar\\b'),
			('foo*', '\\bfoo', '\\bfoo'),
			('*foo*', 'foo', 'foo'),
			('foo+', 'foo\\+', '\\bfoo\\+'),
			(' foo', '\\bfoo', '\\bfoo\\b'),
			('foo ', 'foo\\b', '\\bfoo\\b'),
			(' foo ', '\\bfoo\\b', '\\bfoo\\b'),
			(' foo bar ', '\\bfoo\\W+bar\\b', '\\bfoo\\W+bar\\b'),
			('\u4e00foo*', '\u4e00foo', '\\b\u4e00foo'), # chinese char never wants implicit word boundary
			('*\u4e00foo', '\u4e00foo\\b', '\u4e00foo\\b'),
			(' \u4e00foo', '\\b\u4e00foo', '\\b\u4e00foo\\b'),
			('+foo*', '\\+foo', '\\+foo'), # no word boundery at non-word character
			('Lorem ip* dolor', '\\bLorem\\W+ip\\S*\\W+dolor\\b', '\\bLorem\\W+ip\\S*\\W+dolor\\b'),
			('Lorem *sum dolor', '\\bLorem\\W+\\S*sum\\W+dolor\\b', '\\bLorem\\W+\\S*sum\\W+dolor\\b'),
		):
			self.assertEqual(search_query_term_to_regex(_t('kw', value)), re.compile(regex, re.I), msg="Query: %r" % value)
			self.assertEqual(search_query_term_to_regex(_t('kw', value), flags=SEARCH_WHOLE_WORD), re.compile(regex_word, re.I), msg="Query: %r" % value)
			self.assertEqual(search_query_term_to_regex(_t('kw', value, kw_operator=OPERATOR_EQUAL)), re.compile(regex))
			self.assertEqual(search_query_term_to_regex(_t('kw', value), flags=SEARCH_CASE_SENSITIVE), re.compile(regex))
			self.assertEqual(search_query_term_to_regex(_t('kw', value), flags=SEARCH_CASE_SENSITIVE|SEARCH_WHOLE_WORD), re.compile(regex_word))


class TestSearchQueryPageNameTermToRegex(tests.TestCase):

	def runTest(self):
		for value, regex, regex_word in (
			('foo', 'foo', '\\bfoo\\b'),
			(' foo', '\\bfoo', '\\bfoo\\b'),
			('*foo', 'foo\\b', 'foo\\b'),
			('foo bar', 'foo\\W+bar', '\\bfoo\\W+bar\\b'),
			('foo*', '\\bfoo', '\\bfoo'),
			('foo+', 'foo\\+', '\\bfoo\\+'),
			('foo ', 'foo\\b', '\\bfoo\\b'),
			(' foo ', '\\bfoo\\b', '\\bfoo\\b'),
			('*foo*', 'foo', 'foo'),
			(' foo bar ', '\\bfoo\\W+bar\\b', '\\bfoo\\W+bar\\b'),
			(' foo*bar ', '\\bfoo[^\\s:]*bar\\b', '\\bfoo[^\\s:]*bar\\b'),
			(':foo:', '(^:?|:)foo(:|:?$)', '(^:?|:)foo(:|:?$)'),
			('::foo::', '^:?foo:?$', '^:?foo:?$'),
			('::foo:+', '^:?foo:.+', '^:?foo:.+'),
		):
			self.assertEqual(search_query_pagename_term_to_regex(_t('kw', value)), re.compile(regex, re.I), msg="Query: %r" % value)
			self.assertEqual(search_query_pagename_term_to_regex(_t('kw', value), flags=SEARCH_WHOLE_WORD), re.compile(regex_word, re.I), msg="Query: %r" % value)
			self.assertEqual(search_query_pagename_term_to_regex(_t('kw', value, kw_operator=OPERATOR_EQUAL)), re.compile(regex))
			self.assertEqual(search_query_pagename_term_to_regex(_t('kw', value), flags=SEARCH_CASE_SENSITIVE), re.compile(regex))
			self.assertEqual(search_query_pagename_term_to_regex(_t('kw', value), flags=SEARCH_CASE_SENSITIVE|SEARCH_WHOLE_WORD), re.compile(regex_word))


class TestSearchQueryTagsTermToRegex(tests.TestCase):

	def runTest(self):
		for value, regex, regex_word in (
			('foo', 'foo', '\\bfoo\\b'),
			('foo*', '\\bfoo', '\\bfoo'),
			('*foo', 'foo\\b', 'foo\\b'),
			('*foo*', 'foo', 'foo'),
			('foo*bar', '\\bfoo\\S*bar\\b', '\\bfoo\\S*bar\\b'),
			('foo+', 'foo\\+', '\\bfoo\\+'),
			('@foo', '\\bfoo', '\\bfoo\\b'),
			('foo@', 'foo\\b', '\\bfoo\\b'),
			('@foo@', '\\bfoo\\b', '\\bfoo\\b')
		):
			self.assertEqual(search_query_tags_term_to_regex(_t('kw', value)), re.compile(regex, re.I), msg="Query: %r" % value)
			self.assertEqual(search_query_tags_term_to_regex(_t('kw', value), flags=SEARCH_WHOLE_WORD), re.compile(regex_word, re.I), msg="Query: %r" % value)
			self.assertEqual(search_query_tags_term_to_regex(_t('kw', value, kw_operator=OPERATOR_EQUAL)), re.compile(regex, re.I))
			self.assertEqual(search_query_tags_term_to_regex(_t('kw', value), flags=SEARCH_CASE_SENSITIVE), re.compile(regex, re.I))
			self.assertEqual(search_query_tags_term_to_regex(_t('kw', value), flags=SEARCH_CASE_SENSITIVE|SEARCH_WHOLE_WORD), re.compile(regex_word, re.I))


class TestSearchQueryToFindQuery(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook()
		page_search = PageSearch(notebook)

		for string, value in (
			('Foo', 'Foo'),
			('*Foo*', '*Foo*'),
			('" Foo "', ' Foo '),
			('Foo Bar', 'Foo|Bar'),
			('Foo -Bar', 'Foo'), # Bar negated
			('Links: Foo', None), # no content match in this query
			('Tag: Foo', '@Foo '),
			('@Foo', '@Foo'),
			('@Foo Bar', '@Foo|Bar'),
			('Foo... Bar', 'Foo...|Bar'),
			('"Foo... Bar"', 'Foo... Bar'),
			('NOT foo', None),
			('Foo*Bar', 'Foo*Bar'),
			('*Foo*Bar*', '*Foo*Bar*'),
			('Foo AND (Bar OR Dus)', 'Foo|Bar|Dus'),
			('Foo AND NOT (Bar OR Dus)', 'Foo'),
		):
			squery = page_search.parse_page_search_query(string)
			fquery = page_search.find_query_from_search_query(squery)
			self.assertEqual(fquery.string if fquery else fquery, value, msg="Query: %r" % string)


class TestPageSearchProviders(tests.TestCase):
	'''Test `generate`, `filter`, and `checker` interface for providers'''

	def assertProviderResults(self, provider, paths):
		self.assertResultsMatch(list(provider.generate()), paths)
		self.assertResultsMatch(list(provider.filter(provider.walk_notebook())), paths)
		check = provider.checker()
		self.assertResultsMatch(list(r for r in provider.walk_notebook() if check(r)), paths)

		if hasattr(provider, 'SUPPORTS_NEGATE') and provider.SUPPORTS_NEGATE:
			# HACK to create negated version
			negterm = provider.term
			negterm.negate = not negterm.negate
			provider = provider.__class__(provider.notebook, negterm)
			#
			self.assertResultsExclude(list(provider.generate()), paths)
			self.assertResultsExclude(list(provider.filter(provider.walk_notebook())), paths)
			check = provider.checker()
			self.assertResultsExclude(list(r for r in provider.walk_notebook() if check(r)), paths)

	def assertResultsMatch(self, results, paths):
		self.assertTrue(all(isinstance(r, PageSearchResult) for r in results), 'Got: %r' % results)
		self.assertEqual(set(r.path.name for r in results), set(Path(p).name for p in paths))

	def assertResultsExclude(self, results, paths):
		self.assertTrue(all(isinstance(r, PageSearchResult) for r in results), 'Got: %r' % results)
		self.assertTrue(results is not None, 'Good test case should have positive negated values')
		self.assertTrue(set(r.path.name for r in results).isdisjoint(set(Path(p).name for p in paths)))

	def testPageNameProvider(self):
		content = ('Test', 'FooBar', 'baz', 'Dus', 'Test:Bar')
		query = 'ba'
		match = ('FooBar', 'baz', 'Test:Bar')
		nomatch = ('Test', 'Dus')

		notebook = self.setUpNotebook(content=content)
		self.assertProviderResults(PageNameProvider(notebook, SearchQueryTerm('name', query)), match)
		self.assertProviderResults(PageNameProvider(notebook, SearchQueryTerm('name', query), flags=SEARCH_CASE_SENSITIVE), ('baz',))
		self.assertProviderResults(PageNameProvider(notebook, SearchQueryTerm('name', query, negate=True)), nomatch)

		self.assertProviderResults(PageNameProvider(notebook, SearchQueryTerm('name', 'te')), ('Test', 'Test:Bar')) # test matching sub-page as well

		# Check handling section and namespace keywords
		for kw in ('section', 'namespace'):
			provider = PageNameProvider(notebook, SearchQueryTerm(kw, query))
			self.assertEqual(provider.regex, search_query_pagename_term_to_regex(_t('kw', '::ba:')))

	def testLinksProvider(self):
		content = {
			'Test1': 'xyz',
			'Foo': 'bar [[Dest]]',
			'Bar': 'foo',
			'LinkToFoo': '[[Foo]]',
			'Dest': 'xyz',
		}
		query = 'Foo'
		matchfrom = ('Dest', 'Foo') # 'Foo' is in here because 'LinkToFoo' also matches pagename query 'Foo'
		matchto = ('LinkToFoo',)

		notebook = self.setUpNotebook(content=content)
		self.assertProviderResults(LinksProvider(notebook, SearchQueryTerm('links', query)), matchfrom)
		self.assertProviderResults(LinksProvider(notebook, SearchQueryTerm('linksfrom', query)), matchfrom)
		self.assertProviderResults(LinksProvider(notebook, SearchQueryTerm('links', query), flags=SEARCH_WHOLE_WORD), ('Dest',)) # LinkToFoo no longer matches

		self.assertProviderResults(LinksProvider(notebook, SearchQueryTerm('linksto', query)), matchto)
		self.assertFalse(LinksProvider.SUPPORTS_NEGATE) # else test here

	def testTagsProviderBackward(self):
		# Backward compatibility with exact match
		content = {'Page1': '@foo', 'Page2': '@foo @bar', 'Page3': '', 'Page4': '@bar'}
		notebook = self.setUpNotebook(content=content)
		self.assertProviderResults(TagsProvider(notebook, SearchQueryTerm('tag', '@foo')), ('Page1', 'Page2'))
		self.assertProviderResults(TagsProvider(notebook, SearchQueryTerm('tag', 'foo')), ('Page1', 'Page2'))

	def testTagsProvider(self):
		content = {'A': '@projectA', 'B': '@projectB', 'some': '@someproject', 'project': '@PROJECT', 'empty': ''}
		notebook = self.setUpNotebook(content=content)
		self.assertProviderResults(TagsProvider(notebook, SearchQueryTerm('tags', 'project')), ('A', 'B', 'some', 'project'))
		self.assertProviderResults(TagsProvider(notebook, SearchQueryTerm('tags', 'project'), flags=SEARCH_CASE_SENSITIVE), ('A', 'B', 'some', 'project')) # tags always case in-sensitive
		self.assertProviderResults(TagsProvider(notebook, SearchQueryTerm('tags', 'project'), flags=SEARCH_WHOLE_WORD), ('project',))

		self.assertProviderResults(TagsProvider(notebook, SearchQueryTerm('tags', '@project')), ('A', 'B', 'project'))
		self.assertProviderResults(TagsProvider(notebook, SearchQueryTerm('tags', '@project@')), ('project',))

	def testTextProvider(self, cls=TextProvider):
		# Also used by test for FTS plugin below
		notebook = self.setUpNotebook(content={'test1': 'foo', 'test2': 'barfoo', 'test3': 'Foobar', 'test4': 'foo**bar**'})
		self.assertProviderResults(cls(notebook, SearchQueryTerm('text', 'foo')), ('test1', 'test2', 'test3', 'test4'))
		self.assertProviderResults(cls(notebook, SearchQueryTerm('text', ' foo')), ('test1', 'test3', 'test4'))
			# test2 does not match due to not starts word
		self.assertProviderResults(cls(notebook, SearchQueryTerm('text', 'foo'), flags=SEARCH_WHOLE_WORD), ('test1',))
		self.assertProviderResults(cls(notebook, SearchQueryTerm('text', 'foo'), flags=SEARCH_CASE_SENSITIVE), ('test1', 'test2', 'test4'))
		self.assertProviderResults(cls(notebook, SearchQueryTerm('text', 'foo*bar')), ('test3', 'test4'))
			# to match test4, search should ignore formatting

	def testProvidersInKeywords(self):
		# Catch if provider is added without tets case here
		tested = (PageNameProvider, LinksProvider, TagsProvider, TextProvider)
		for attr in PageSearch._KEYWORDS.values():
			if 'provider' in attr:
				self.assertIn(attr['provider'], tested)
			else:
				self.assertIn('expand_terms', attr)

	def testAndGroup(self):
		notebook = self.setUpNotebook(content=('FooBar', 'Foo', 'Bar'))
		andgroup = AndGroup(notebook, [
			PageNameProvider(notebook, SearchQueryTerm('name', 'foo')),
			PageNameProvider(notebook, SearchQueryTerm('name', 'bar'))
		])
		self.assertProviderResults(andgroup, ('FooBar',))

	def testOrGroup(self):
		notebook = self.setUpNotebook(content=('FooBar', 'Foo', 'Bar', 'test', 'dus'))
		orgroup = OrGroup(notebook, [
			PageNameProvider(notebook, SearchQueryTerm('name', 'foo')),
			PageNameProvider(notebook, SearchQueryTerm('name', 'bar'))
		])
		self.assertProviderResults(orgroup, ('FooBar', 'Foo', 'Bar'))

	def testNegateOperator(self):
		notebook = self.setUpNotebook(content=('FooBar', 'Foo', 'Bar'))
		andgroup = AndGroup(notebook, [
			PageNameProvider(notebook, SearchQueryTerm('name', 'foo')),
			PageNameProvider(notebook, SearchQueryTerm('name', 'bar'))
		])
		negate = NegateOperator(andgroup)
		self.assertProviderResults(negate, ('Foo', 'Bar'))


class TestPageSearch(tests.TestCase):

	@classmethod
	def setUpClass(cls):
		# Using a class setup speeds up considerably when testing with real files
		cls.notebook = cls.setUpClassNotebook(content=tests.FULL_NOTEBOOK)

	def testDefaultKeyword(self):
		page_search = PageSearch(self.notebook)

		query = page_search.parse_page_search_query('foo bar')
		self.assertEqual(query, _and(_t('any', 'foo'), _t('any', 'bar')))
		results = list(r.path for r in page_search.search_pages(query))
		self.assertTrue(len(results) > 0)
		self.assertFalse(Path('TaskList:foo') in results)
		self.assertTrue(Path('Test:foo') in results)
		self.assertTrue(Path('Test:foo:bar') in results)

		query = page_search.parse_page_search_query('foo bar', flags=SEARCH_CASE_SENSITIVE)
		case_results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(len(case_results) > 0)
		self.assertTrue(len(case_results) < len(results)) # test flags are passed on

		query = page_search.parse_page_search_query('+TODO -bar')
		self.assertEqual(query, _and(_t('any', 'TODO'), _not(_t('any', 'bar'))))
		query = page_search.parse_page_search_query('TODO not bar')
		self.assertEqual(query, _and(_t('any', 'TODO'), _not(_t('any', 'bar'))))
		results = list(r.path for r in page_search.search_pages(query))
		self.assertTrue(len(results) > 0)
		self.assertTrue(Path('TaskList:foo') in results)
		self.assertFalse(Path('TaskList:all') in results)
		self.assertFalse(Path('Test:foo') in results)
		self.assertFalse(Path('Test:foo:bar') in results)

		query = page_search.parse_page_search_query('TODO or bar')
		self.assertEqual(query, _or(_t('any', 'TODO'), _t('any', 'bar')))
		results = list(r.path for r in page_search.search_pages(query))
		self.assertTrue(len(results) > 0)
		self.assertTrue(Path('TaskList:foo') in results)
		self.assertTrue(Path('Test:foo') in results)
		self.assertTrue(Path('Test:foo:bar') in results)

		query = page_search.parse_page_search_query('ThisWordDoesNotExistingInTheTestNotebook')
		results = list(r.path for r in page_search.search_pages(query))
		self.assertFalse(results)

	def testContentKeyword(self):
		page_search = PageSearch(self.notebook)
		query = page_search.parse_page_search_query('Content: foo')
		self.assertEqual(query, _q(_t('content', 'foo')))
		results = list(page_search.search_pages(query))
		self.assertTrue(len(results) > 0)

	def testNameKeyword(self):
		page_search = PageSearch(self.notebook)

		query = page_search.parse_page_search_query('Name: foo')
		self.assertEqual(query, _q(_t('name', 'foo')))
		results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(len(results) > 0)

		query = page_search.parse_page_search_query('Name: foo', flags=SEARCH_CASE_SENSITIVE)
		self.assertEqual(query, _q(_t('name', 'foo')))
		case_results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(len(case_results) > 0)
		self.assertTrue(len(case_results) < len(results))

	def testSectionKeyword(self):
		page_search = PageSearch(self.notebook)

		query = page_search.parse_page_search_query('Namespace: "TaskList" fix')
		self.assertEqual(query, _and(_t('namespace', 'TaskList'), _t('any', 'fix')))
		results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(Path('TaskList:foo') in results)

		for text in (
			'Namespace: "Test:Foo Bar"',
			'Namespace:"Test:Foo Bar"'
			'Section: "Test:Foo Bar"'
			'Section:"Test:Foo Bar"'
		):
			# check if space in page name works - found bug for 2nd form
			query = page_search.parse_page_search_query(text)
			results = [r.path for r in page_search.search_pages(query)]
			self.assertTrue(Path('Test:Foo Bar:Dus Ja Hmm') in results)

		query = page_search.parse_page_search_query('Namespace: "NonExistingNamespace"')
		results = [r.path for r in page_search.search_pages(query)]
		self.assertFalse(results)

	def testTagKeyword(self):
		page_search = PageSearch(self.notebook)

		query = page_search.parse_page_search_query('Tag: tags')
		self.assertEqual(query, _q(_t('tag', 'tags')))
		results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(Path('Test:tags') in results and len(results) == 2)
			# Tasklist:all is the second match

		query = page_search.parse_page_search_query('Tag: NonExistingTag')
		results = [r.path for r in page_search.search_pages(query)]
		self.assertFalse(results)

	def testTagsKeyword(self):
		page_search = PageSearch(self.notebook)

		query = page_search.parse_page_search_query('Tags: tags')
		self.assertEqual(query, _q(_t('tags', 'tags')))

		query = page_search.parse_page_search_query('@tags') # implicit keyword
		self.assertEqual(query, _q(_t('tags', '@tags')))
		results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(Path('Test:tags') in results and len(results) == 2)
			# Tasklist:all is the second match

		query = page_search.parse_page_search_query('Tag: NonExistingTag')
		results = [r.path for r in page_search.search_pages(query)]
		self.assertFalse(results)

		# more implicit
		query = page_search.parse_page_search_query('@tags*foo@')
		self.assertEqual(query, _q(_t('tags', '@tags*foo@')))

	def testLinksToKeyword(self):
		page_search = PageSearch(self.notebook)

		query = page_search.parse_page_search_query('LinksTo: "Linking:Foo:Bar"')
		self.assertEqual(query, _and(_t('linksto', 'Linking:Foo:Bar')))
		results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(Path('Linking:Dus:Ja') in results)

		query = page_search.parse_page_search_query('NOT LinksTo:"Linking:Foo:Bar"')
		self.assertEqual(query, _q(_not(_t('linksto', 'Linking:Foo:Bar'))))
		results = [r.path for r in page_search.search_pages(query)]
		self.assertFalse(Path('Linking:Dus:Ja') in results)

		query = page_search.parse_page_search_query('LinksTo:"NonExistingNamespace:*"')
		results = [r.path for r in page_search.search_pages(query)]
		self.assertFalse(results)

	def testLinksFromKeyword(self):
		page_search = PageSearch(self.notebook)

		query = page_search.parse_page_search_query('LinksFrom: "Linking:Dus:Ja"')
		self.assertEqual(query, _q(_t('linksfrom', 'Linking:Dus:Ja')))
		results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(Path('Linking:Foo:Bar') in results)

		query = page_search.parse_page_search_query('Links: "Linking:Dus:Ja"') # alias for LinksFrom
		self.assertEqual(query, _q(_t('links', 'Linking:Dus:Ja')))
		results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(Path('Linking:Foo:Bar') in results)

		query = page_search.parse_page_search_query('LinksFrom:"NonExistingNamespace:*"')
		results = [r.path for r in page_search.search_pages(query)]
		self.assertFalse(results)

	def testQuotedString(self):
		page_search = PageSearch(self.notebook)
		query = page_search.parse_page_search_query('"Lorem ipsum dolor"')
		results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(Path('roundtrip') in results)

		query = page_search.parse_page_search_query('"Lorem ip* dolor"')
		results = [r.path for r in page_search.search_pages(query)]
		self.assertTrue(Path('roundtrip') in results)

	def testCaseSensitive(self):
		page_search = PageSearch(self.notebook)
		query = page_search.parse_page_search_query('Content: foo')
		results = [(r.path, r.search_score) for r in page_search.search_pages(query)]

		query = page_search.parse_page_search_query('Content:= foo')
		results_sensitive = [(r.path, r.search_score) for r in page_search.search_pages(query)]

		self.assertNotEqual(results_sensitive, results)

	def testFindQuery(self):
		# Has seperate test case with more queries, test here to make sure
		# plugin tests deriving from this class also check it
		page_search = PageSearch(self.notebook)
		query = page_search.parse_page_search_query('foo bar', SEARCH_CASE_SENSITIVE)
		self.assertEqual(query, _and(_t('any', 'foo'), _t('any', 'bar')))
		fquery = page_search.find_query_from_search_query(query)
		self.assertEqual(fquery, FindQuery('foo|bar', SEARCH_CASE_SENSITIVE))


@tests.slowTest
class TestPageSearchFiles(TestPageSearch):

	@classmethod
	def setUpClass(cls):
		# Using a class setup speeds up considerably when testing with real files
		cls.notebook = cls.setUpClassNotebook(mock=tests.MOCK_ALWAYS_REAL, content=tests.FULL_NOTEBOOK)


@tests.skipIf(
	indexed_fts.IndexedFTSPlugin.check_dependencies()[0] == False,
	"Indexed FTS plugin not available"
)
class TestPageSearchIndexed(TestPageSearch):
	'''Test case for integration with the indexed_fts plugin'''

	@classmethod
	def setUpClass(cls):
		tests.TestCase.setUpClass() # setup plugin manager
		PluginManager.load_plugin('indexed_fts')
		TestPageSearch.setUpClass()

	def testProvider(self):
		TestPageSearchProviders().testTextProvider(cls=indexed_fts.FTSSearchProvider)

		term = _t('content', 'foo')
		self.assertEqual(indexed_fts.FTSSearchProvider.get_find_string(term), 'foo')


class TestUnicodeSearchTerms(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook(content={'Öffnungszeiten': 'Öffnungszeiten ... 123\n'})
		page_search = PageSearch(notebook)
		path = Path('Öffnungszeiten')
		for string in (
			'*zeiten', # no unicode - just check test case
			'Öffnungszeiten',
			'öffnungszeiten', # case insensitive version
			'content:Öffnungszeiten',
			'content:öffnungszeiten',
			'name:Öffnungszeiten',
			'name:öffnungszeiten',
			'content:Öff*',
			'content:öff*',
			'name:Öff*',
			'name:öff*',
		):
			query = page_search.parse_page_search_query(string)
			results = [r.path for r in page_search.search_pages(query)]
			self.assertIn(path, results, 'query did not match: "%s"' % string)


class TestQueryGrouping(tests.TestCase):

	PAGES = {
		'page1': 'term1',
		'page2': 'term2',
		'page3': 'term3',
		'page4': 'term4',
		'page12': 'term1 term2',
		'page13': 'term1 term3',
	}

	def runTest(self):
		notebook = self.setUpNotebook(content=self.PAGES)
		page_search = PageSearch(notebook)
		for string, pages in (
			('term1', ('page1', 'page12', 'page13')), # simpel case to test test construct
			('term1 term2', ('page12',)),
			('term1 AND term2', ('page12',)),
			('term1 term2 OR term3', ('page12', 'page13')),
			('term1 (term2 OR term3)', ('page12', 'page13')),
			('(term1 term2) OR term3', ('page12', 'page3', 'page13')),
			('term1 NOT (term2 OR term3)', ('page1',)), # includes transform of `NOT (a OR b)` to `NOT a AND NOT b`
			('term1 NOT (term1 AND term3)', ('page1', 'page12')), # includes transform of `NOT (a OR b)` to `NOT a AND NOT b`
		):
			query = page_search.parse_page_search_query(string)
			results = set(r.path for r in page_search.search_pages(query))
			self.assertEqual(results, set(Path(p) for p in pages))


class TestUICallbackCancel(tests.TestCase):

	def runTest(self):
		def callback():
			raise SearchCancelledException

		content = dict(('page%i' % i, 'foo') for i in range(10))
		notebook = self.setUpNotebook(content=content)
		page_search = PageSearch(notebook, ui_callback=callback)
		results = list(page_search.search_pages(page_search.parse_page_search_query('content: foo')))
		self.assertEqual(len(results), UI_CALLBACK_RATE_FOR_CONTENT) # should be cancelled at first callback


class TestCompileSearchQueryCheckFunction(tests.TestCase):

	tuple_keywords = {
		'name': {'check_func_constructor': check_func_constructor_any_keyword, 'include': ('firstname', 'lastname')},
		'firstname': {'key': 0},
		'lastname': {'key': 1}
	}
	dict_keywords = {
		'name': {'check_func_constructor': check_func_constructor_any_keyword, 'include': ('firstname', 'lastname')},
		'firstname': {'key': 'f_name'},
		'lastname': {'key': 'lastname'}
	}
	tuple_records = [
		('John', 'Doe'),
		('Johnny', 'Doe'),
		('John', 'Johnson'),
		('Janna', 'Doe'),
	]
	dict_records = [
		{'f_name': 'John', 'lastname': 'Doe'},
		{'f_name': 'Johnny', 'lastname': 'Doe'},
		{'f_name': 'John', 'lastname': 'Johnson'},
		{'f_name': 'Janna', 'lastname': 'Doe'},
	]
	queries = [
		('John', [True, True, True, False]),
		('name:John', [True, True, True, False]),
		('name: John', [True, True, True, False]),
		('name: "John"', [True, True, True, False]),
		('name: "John "', [True, False, True, False]),
		('firstname:John', [True, True, True, False]),
		('lastname:John', [False, False, True, False]),
		('firstname:John and lastname:Doe', [True, True, False, False]),
		('firstname:John or lastname:Doe', [True, True, True, True]),
		('not John', [False, False, False, True]),
	]

	def testWithTupleRecords(self):
		self._runTest(self.tuple_keywords, self.tuple_records)

	def testWithDictRecords(self):
		self._runTest(self.dict_keywords, self.dict_records)

	def _runTest(self, keywords, records):
		for query, wanted in self.queries:
			p_query = parse_search_query(query, keywords, default_keyword='name')
			#print('>>>', query, '\n', '===', p_query)
			check_func = compile_search_query_check_function(p_query, keywords)
			result = list(map(check_func, records))
			self.assertEqual(result, wanted, msg='Query: %s' % query)


class TestCompileSearchQueryComparisonFunction(tests.TestCase):

	keywords = {
		'date': {'key': 0, 'check_func_constructor': check_comparison_func_constructor, 'comparison': str},
		'prio': {'key': 1, 'check_func_constructor': check_comparison_func_constructor, 'comparison': int},
	}
	records = [
		('2020-01-01', 5),
		('2020-05-05', 1),
		('2020-08-08', 2),
		('2020-12-12', 3),
	]
	queries = [
		('date>2020-06-01', [False, False, True, True]),
		('date:>2020-06-01', [False, False, True, True]),
		('date>=2020-06-01', [False, False, True, True]),
		('date:>=2020-06-01', [False, False, True, True]),

		('date<2020-06-01', [True, True, False, False]),
		('date:<2020-06-01', [True, True, False, False]),
		('date<=2020-06-01', [True, True, False, False]),
		('date:<=2020-06-01', [True, True, False, False]),

		('date: 2020-05-05', [False, True, False, False]),
		('date:2020-05-05', [False, True, False, False]),
		('date=2020-05-05', [False, True, False, False]),
		('date= 2020-05-05', [False, True, False, False]),
		('date:=2020-05-05', [False, True, False, False]),

		('date<2020-05-05', [True, False, False, False]),
		('date<=2020-05-05', [True, True, False, False]),
		('date>2020-05-05', [False, False, True, True]),
		('date>=2020-05-05', [False, True, True, True]),

		('-date>2020-06-01', [True, True, False, False]),
		('-date>=2020-06-01', [True, True, False, False]),
		('-date: 2020-05-05', [True, False, True, True]),

		('prio>2', [True, False, False, True]),
		('prio>=2', [True, False, True, True]),
		('prio=2', [False, False, True, False]),
		('prio: 2', [False, False, True, False]),
		('prio<2', [False, True, False, False]),
		('prio<=2', [False, True, True, False]),
	]

	def runTest(self):
		for query, wanted in self.queries:
			p_query = parse_search_query(query, self.keywords)
			#print('>>>', query, '\n', '===', p_query)
			check_func = compile_search_query_check_function(p_query, self.keywords)
			result = list(map(check_func, self.records))
			self.assertEqual(result, wanted, msg='Query: %s' % query)


class TestSearchCommand(tests.TestCase):

	PAGES = {
		'page_a': 'test 123',
		'page_b': 'foo bar',
		'page_c': 'Foo Foo Bar',
		'page_d': 'foobar',
	}

	def runTest(self):
		notebook = self.setUpNotebook(mock=tests.MOCK_ALWAYS_REAL, content=self.PAGES)
		query = 'foo'

		# search query with and without flags
		cmd = SearchCommand('search')
		cmd.parse_options(notebook.folder.uri, query)
		with capture_stdout() as output:
			cmd.run()
		self.assertEqual(output.getvalue(), 'page b\npage c\npage d\n')

		cmd = SearchCommand('search')
		cmd.parse_options('--whole-word', notebook.folder.uri, query)
		with capture_stdout() as output:
			cmd.run()
		self.assertEqual(output.getvalue(), 'page b\npage c\n') # page_d drops out

		cmd = SearchCommand('search')
		cmd.parse_options('--match-case', notebook.folder.uri, query)
		with capture_stdout() as output:
			cmd.run()
		self.assertEqual(output.getvalue(), 'page b\npage d\n') # page_c drops out

		cmd = SearchCommand('search')
		cmd.parse_options('-w', '-c', notebook.folder.uri, query)
		with capture_stdout() as output:
			cmd.run()
		self.assertEqual(output.getvalue(), 'page b\n') # both page_c and page_d drop out

		# sort results
		cmd = SearchCommand('search')
		cmd.parse_options('--sorted', notebook.folder.uri, query)
		with capture_stdout() as output:
			cmd.run()
		self.assertEqual(output.getvalue(), 'page b\npage c\npage d\n')

		# with scores
		cmd = SearchCommand('search')
		cmd.parse_options('--scores', notebook.folder.uri, query)
		with capture_stdout() as output:
			cmd.run()
		self.assertEqual(output.getvalue(), '2\tpage b\n3\tpage c\n2\tpage d\n')

		cmd = SearchCommand('search')
		cmd.parse_options('--scores', '--sorted', notebook.folder.uri, query)
		with capture_stdout() as output:
			cmd.run()
		self.assertEqual(output.getvalue(), '3\tpage c\n2\tpage b\n2\tpage d\n')
