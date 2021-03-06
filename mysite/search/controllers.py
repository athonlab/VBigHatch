import mysite.search.models
import mysite.search.views
import mysite.base.unicode_sanity
import mysite.base.decorators
import collections
import urllib
import re
import sha
from django.db.models import Q

def order_bugs(query):
    # Minus sign: reverse order
    # Minus good for newcomers: this means true values
    # (like 1) appear before false values (like 0)
    # Minus last touched: Old bugs last.
    return query.order_by('-good_for_newcomers', '-last_touched')

class Query:
    
    def __init__(self, terms=None, active_facet_options=None, terms_string=None): 
        self.terms = terms or []
        self.active_facet_options = (mysite.base.decorators.no_str_in_the_dict(active_facet_options)
                                     or {})
        if type(terms_string) == str:
            terms_string = unicode(terms_string, 'utf-8')
        self._terms_string = terms_string

    @property
    def terms_string(self):
        if self._terms_string is None:
            raise ValueError
        return self._terms_string 

    @staticmethod
    def split_into_terms(string):
        # We're given some query terms "between quotes"
        # and some glomped on with spaces.
        # Strategy: Find the strings validly inside quotes, and remove them
        # from the original string. Then split the remainder (and probably trim
        # whitespace from the remaining terms).
        # {{{
        ret = []
        splitted = re.split(r'(".*?")', string)

        for (index, word) in enumerate(splitted):
            if (index % 2) == 0:
                ret.extend(word.split())
            else:
                assert word[0] == '"'
                assert word[-1] == '"'
                ret.append(word[1:-1])

        return ret
        # }}}

    @staticmethod
    def create_from_GET_data(GET):
        possible_facets = [u'language', u'toughness', u'contribution_type',
                           u'project']

        active_facet_options = {}
        for facet in possible_facets:
            if GET.get(facet):
                active_facet_options[facet] = GET.get(facet)
        terms_string = GET.get('q', u'')
        terms = Query.split_into_terms(terms_string)

        return Query(terms=terms, active_facet_options=active_facet_options, terms_string=terms_string)

    def get_bugs_unordered(self):
        return mysite.search.models.Bug.open_ones.filter(self.get_Q())

    def __nonzero__(self):
        if self.terms or self.active_facet_options:
            return 1
        return 0

    def get_Q(self, exclude_active_facets=False):
        """Get a Q object which can be passed to Bug.open_ones.filter()"""

        # Begin constructing a conjunction of Q objects (filters)
        q = Q()

        # toughness facet
        toughness_is_active = ('toughness' in self.active_facet_options.keys())
        exclude_toughness = exclude_active_facets and toughness_is_active
        if (self.active_facet_options.get('toughness', None) == 'bitesize'
                and not exclude_toughness):
            q &= Q(good_for_newcomers=True)

        # language facet
        language_is_active = (u'language' in self.active_facet_options.keys())
        exclude_language = exclude_active_facets and language_is_active
        if u'language' in self.active_facet_options and not exclude_language: 
            language_value = self.active_facet_options[u'language']
            if language_value == 'Unknown':
                language_value=''
            q &= Q(project__language__iexact=language_value)

        # project facet
        project_is_active = (u'project' in self.active_facet_options.keys())
        exclude_project = exclude_active_facets and project_is_active
        if u'project' in self.active_facet_options and not exclude_project:
            project_value = self.active_facet_options[u'project']
            q &= Q(project__name__iexact=project_value)

        # contribution type facet
        contribution_type_is_active = ('contribution_type' in
                                       self.active_facet_options.keys())
        exclude_contribution_type = exclude_active_facets and contribution_type_is_active
        if (self.active_facet_options.get('contribution_type', None) == 'documentation'
                and not exclude_contribution_type):
            q &= Q(concerns_just_documentation=True)

        for word in self.terms:
            whole_word = "[[:<:]]%s($|[[:>:]])" % (
                    mysite.base.controllers.mysql_regex_escape(word))
            terms_disjunction = (
                    Q(project__language__iexact=word) |
                    Q(title__iregex=whole_word) |
                    Q(description__iregex=whole_word) |
                    Q(as_appears_in_distribution__iregex=whole_word) |

                    # 'firefox' grabs 'mozilla firefox'.
                    Q(project__name__iregex=whole_word)
                    )
            q &= terms_disjunction

        return q

    def get_facet_option_data(self, facet_name, option_name):

        # Create a Query for this option. 

        # This Query is sensitive to the currently active facet options...
        GET_data = dict(self.active_facet_options)

        # ...except the toughness facet option in question.
        GET_data.update({
            u'q': unicode(self.terms_string),
            unicode(facet_name): unicode(option_name),
            })
        query_string = mysite.base.unicode_sanity.urlencode(GET_data)
        query = Query.create_from_GET_data(GET_data)
        the_all_option = u'any' 
        name = option_name or the_all_option

        active_option_name = self.active_facet_options.get(facet_name, None)

        # This facet isn't active...
        is_active = False

        # ...unless there's an item in active_facet_options mapping the
        # current facet_name to the option whose data we're creating...
        if active_option_name == option_name:
            is_active = True

        # ...or if this is the 'any' option and there is no active option
        # for this facet.
        if name == the_all_option and active_option_name is None:
            is_active = True

        return {
                'name': name,
                'count': query.get_or_create_cached_hit_count(),
                'query_string': query_string,
                'is_active': is_active
                }
    
    def get_facet_options(self, facet_name, option_names):
        # Assert that there are only unicode strings in this list
        option_names = mysite.base.decorators.no_str_in_the_list(option_names)

        options = [self.get_facet_option_data(facet_name, n) for n in option_names]
        # ^^ that's a list of facet options, where each "option" is a
        # dictionary that looks like this:
        # {
        #   'name': name,
        #   'count': query.get_or_create_cached_hit_count(),
        #   'query_string': query_string,
        #   'is_active': is_active
        # }

        # Now we're gonna sort these dictionaries.
        # Active facet options first. Then non-'Unknowns'. Then by number of
        # bugs. Then alphabetically. 

        # Note that these keys are in ascending order of precedence. So the
        # last one trumps all the previous sortings.

        options.sort(key=lambda x: x['name'])
        # Sort alphabetically by name. (This appears first because it has the
        # lowest precedence.)

        options.sort(key=lambda x: x['count'], reverse=True) # 3 sorts before 50
        # We want facet options that contain lots of bugs to appear at the top.
        # If you sort (naively) by x['count'], then the lower numbers appear
        # higher in the list. Let's reverse that with reverse=True.
        
        options.sort(
                key=lambda x: (facet_name == 'language') and (x['name'] == 'Unknown'))
        # We want the Unknown language to appear last, unless it's active. If
        # the key lambda function returns False, then those options appear
        # first (because False appears before True), which is what we want.

        options.sort(key=lambda x: x['is_active'], reverse=True)
        # We want the value True to sort before the value False. So let's
        # reverse this comparison (because normally False sorts before True,
        # just like zero comes before one).

        return options

    def get_possible_facets(self):

        bugs = mysite.search.models.Bug.open_ones.filter(self.get_Q())

        project_options = self.get_facet_options(u'project', self.get_project_names())

        toughness_options = self.get_facet_options(u'toughness', [u'bitesize'])

        contribution_type_options = self.get_facet_options(
            u'contribution_type', [u'documentation'])

        language_options = self.get_facet_options(u'language', self.get_language_names())
            
        # looks something like:
        # [{'count': 1180L, 'query_string': 'q=&language=Python', 'is_active': False, 'name': u'Python'}, {'count': 478L, 'query_string': 'q=&language=C%23', 'is_active': False, 'name': u'C#'}, {'count': 184L, 'query_string': 'q=&language=Unknown', 'is_active': False, 'name': 'Unknown'}, {'count': 532L, 'query_string': 'q=&language=C', 'is_active': False, 'name': u'C'}, {'count': 2374L, 'query_string': 'q=&language=', 'is_active': True, 'name': 'any'}]

        possible_facets = ( 
                # The languages facet is based on the project languages, "for now"
                (u'language', {
                    u'name_in_GET': u"language",
                    u'sidebar_heading': u"Languages",
                    u'description_above_results': u"projects primarily coded in %s",
                    u'options': language_options,
                    u'the_any_option': self.get_facet_options(u'language', [u''])[0],
                    }),
                (u'project', {
                    u'name_in_GET': u'project',
                    u'sidebar_heading': u'Projects',
                    u'description_above_results': 'in the %s project',
                    u'options': project_options,
                    u'the_any_option': self.get_facet_options(u'project', [u''])[0],
                }),
                (u'toughness', {
                    u'name_in_GET': u"toughness",
                    u'sidebar_heading': u"Toughness",
                    u'description_above_results': u"where toughness = %s",
                    u'options': toughness_options,
                    u'the_any_option': self.get_facet_options(u'toughness', [u''])[0],
                }),
                (u'contribution type', {
                    u'name_in_GET': u"contribution_type",
                    u'sidebar_heading': u"Just bugs labeled...",
                    u'description_above_results': u"which need %s",
                    u'options': contribution_type_options,
                    u'the_any_option': self.get_facet_options(u'contribution_type', [u''])[0],
                    })
            )

        return possible_facets

    def get_GET_data(self):
        GET_data = {u'q': unicode(self.terms_string)}
        GET_data.update(self.active_facet_options)
        return GET_data

    def get_language_names(self):

        GET_data = self.get_GET_data()
        if u'language' in GET_data:
            del GET_data[u'language']
        query_without_language_facet = Query.create_from_GET_data(GET_data)

        bugs = query_without_language_facet.get_bugs_unordered()
        distinct_language_columns = bugs.values(u'project__language').distinct()
        languages = [x[u'project__language'] for x in distinct_language_columns]
        languages = [l or u'Unknown' for l in languages]

        # Add the active language facet, if there is one
        if u'language' in self.active_facet_options:
            active_language = self.active_facet_options[u'language']
            if active_language not in languages:
                languages.append(active_language)

        return languages

    def get_active_facet_options_except_toughness(self):
        if 'toughness' not in self.active_facet_options:
            return self.active_facet_options

        options = self.active_facet_options.copy()
        del options['toughness']
        return options
  
    def get_project_names(self):
        from django.db.models import Count
        Project = mysite.search.models.Project

        GET_data = self.get_GET_data()
        if u'project' in GET_data:
            del GET_data[u'project']
        query_without_project_facet = Query.create_from_GET_data(GET_data)

        bugs = query_without_project_facet.get_bugs_unordered()
        project_ids = list(bugs.values_list(u'project__id', flat=True).distinct())
        projects = Project.objects.filter(id__in=project_ids)
        project_names = [project.name or u'Unknown' for project in projects]

        # Add the active project facet, if there is one
        if u'project' in self.active_facet_options:
            name_of_active_project = self.active_facet_options[u'project']
            if name_of_active_project not in project_names:
                project_names.append(name_of_active_project)

        return project_names

    def get_sha1(self):

        # first, make a dictionary mapping strings to strings
        simple_dictionary = {}

        # add terms_string
        simple_dictionary[u'terms'] = str(sorted(self.terms))

        # add active_facet_options
        simple_dictionary[u'active_facet_options'] = str(sorted(self.active_facet_options.items()))

        stringified = str(sorted(simple_dictionary.items()))
        # then return a hash of our sorted items self.
        return sha.sha(stringified).hexdigest() # sadly we cause a 2x space blowup here
    
    def get_or_create_cached_hit_count(self):
        hashed_query = self.get_sha1()

        existing_hccs = mysite.search.models.HitCountCache.objects.filter(hashed_query=hashed_query)
        if existing_hccs:
            hcc = existing_hccs[0]
        else:
            count = self.get_bugs_unordered().count()
            hcc, _ = mysite.search.models.HitCountCache.objects.get_or_create(
                    hashed_query=hashed_query,
                    defaults={'hit_count': count})
        return hcc.hit_count

    def get_query_string(self):
        GET_data = self.get_GET_data()
        query_string = mysite.base.unicode_sanity.urlencode(GET_data)
        return query_string

       
def get_project_count():
    """Retrieve the number of projects currently indexed."""
    bugs = mysite.search.models.Bug.all_bugs.all()
    return bugs.values(u'project').distinct().count()

def get_projects_with_bugs():
    bugs = mysite.search.models.Bug.all_bugs.all()
    one_bug_dict_per_project = bugs.values(u'project').distinct().order_by(u'project__name')
    #project_names = [b[u'project__name'] for b in one_bug_dict_per_project]
    projects = []
    for bug_dict in one_bug_dict_per_project:
        pk = bug_dict[u'project']
        projects.append(mysite.search.models.Project.objects.get(pk=pk))
    return projects

def get_cited_projects_lacking_bugs():
    portfolio_entries = mysite.profile.models.PortfolioEntry.published_ones.all()
    one_pfe_dict_per_project = portfolio_entries.values(u'project').distinct().order_by(u'project__name')

    projects_with_contributors = []
    for pfe_dict in one_pfe_dict_per_project:
        pk = pfe_dict[u'project']
        projects_with_contributors.append(mysite.search.models.Project.objects.get(pk=pk))

    projects_with_bugs = get_projects_with_bugs()
    return [p for p in projects_with_contributors if p not in projects_with_bugs]
