from mysite.search.views import get_bugs_by_query_words
from itertools import izip, cycle, islice

## roundrobin() taken from http://docs.python.org/library/itertools.html

def roundrobin(*iterables):
    "roundrobin('ABC', 'D', 'EF') --> A D E B F C"
    # Recipe credited to George Sakkis
    pending = len(iterables)
    nexts = cycle(iter(it).next for it in iterables)
    while pending:
        try:
            for next in nexts:
                yield next()
        except StopIteration:
            pending -= 1
            nexts = cycle(islice(nexts, pending))

def recommend_bugs(queries, n):
    '''Input: A list of queries, like ['Python', 'C#'], designed for use in the search engine.

    I am a generator that yields Bug objects.
    
    I yield up to n Bugs in a round-robin fashion. I don't yield a Bug more than once.'''

    distinct_ids = set()

    various_queries = [get_bugs_by_query_words([t]) for t in queries]
    number_emitted = 0
        
    for bug in roundrobin(*various_queries):
        if number_emitted >= n:
            raise StopIteration
        if bug.id not in distinct_ids:
            number_emitted += 1
            distinct_ids.add(bug.id)
            yield bug