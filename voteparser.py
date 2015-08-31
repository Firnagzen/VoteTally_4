import re, os, errno, signal
from functools import wraps
from itertools import chain, groupby
from bbcodeparser import BBCodeParser
# from difflib import get_close_matches
from collections import OrderedDict, deque
from string import ascii_uppercase, ascii_lowercase, punctuation, whitespace



class TimeoutError(Exception):
    pass


class LUOrderedDict(OrderedDict):
    'Store items in the order the keys were last added'
    def __setitem__(self, key, value):
        if key in self:
            del self[key]
        OrderedDict.__setitem__(self, key, value)



class VoteContainer(object):
    def __init__(self):
        self.defaults = {
            "sim_cutoff"         : 0.95,
            "break_level"        : 0, # 0=entire vote, 1=blocks, 2=lines
            "refer_dir"          : 0, # 0=both, 1=up then both
            "vote_marker"        : "\[[Xx✅✓✓]\]", #regex
            "instant_runoff"     : 0,
            "sort_highest"       : 0
        }

        self.BBparse = BBCodeParser()

        self.rd = str.maketrans(
            ascii_uppercase, ascii_lowercase, 
            punctuation + whitespace)

        self.vote_format = "{}\n[b]No. of voters: {}[/b]\n{}"
        self.voter_format = "[post={}]{}[/post]"

        self.rem_text = set(["quote", "spoiler", "s"])
        self.rem_text_check = set(["quote", "spoiler", "[s]"])

        self.vote_fourple ="vote_bbcode", "vote_plain", "vote_reduced", "marker"
        self.generators = [None, self.break_blocks, self.break_lines]


    def settings(self, **kwargs):
        """Refreshes settings"""
        self.__dict__.update(self.defaults)
        self.__dict__.update(kwargs)
        
        # if self.instant_runoff:
        #     self.vote_marker = "\[([A-Za-z]+)\]\[([0-9]+)\]"

        self.break_generator = self.generators[self.break_level]

        self.vote_re = re.compile('^(\W*){}'.format(self.vote_marker))


    def is_vote(self, test):
        """Helper function to test if the line is a vote"""
        return self.vote_re.match(test)


    def vote_from_text(self, post):
        """Extracts vote, returns a list of the parsed vote and plain text vote.
        Tidies up BBCode. Currently ignores all quoted text."""
        ppost = self.BBparse.parse_tags(post)

        plower = post.lower()
        rem = []
        if any((i in plower) for i in self.rem_text_check):
            rem = self.BBparse.index_tag_pairs(ppost, self.rem_text)

        vote, vote_plain = self.BBparse.line_extract(ppost, self.is_vote, rem)
        return vote, vote_plain


    # def similar_posts(self, a, b):
    #     """Finds a close enough match between a and list if applicable"""
    #     # Nb. Check similarity without BBCode tags
    #     # Nb. Check this for performance
    #     return get_close_matches(a, b, 1, self.sim_cutoff)


    def reduce(self, text):
        """Removes all non alphanumeric values"""
        text = self.vote_re.sub("", text)
        return text.translate(self.rd)


    def extract_votes(self, post_list):
        "Takes lists of posts, returns list of dictionaries containing votes."
        vote_list = deque()
        for post in post_list:
            if "#####" in post['message']:
                continue

            vote_bbcode, vote_plain = self.vote_from_text(post['message'])

            if vote_bbcode:
                vote = {
                    "vote_bbcode"    : vote_bbcode,
                    "vote_plain"     : vote_plain,
                    "voters"         : [post['username']],
                    "voters_reduced" : [self.reduce(post['username'])],
                    "voters_full"    : [(post['username'], post['post_id'])],
                    "vote_reduced"   : [self.reduce(i) for i in vote_plain]
                }

                if self.break_level or self.instant_runoff:
                    vote["marker"] = [self.vote_re.match(i) for i in vote_plain]
                else:
                    vote["marker"] = [None for i in vote_plain]

                vote_list.append(vote)

        return vote_list


    def normalize_by_name(self, line, vote_dict, level = 5):
        """Recurses through vote_dict up to level times to get to the bottom of
        referral chains."""
        vote = vote_dict[line]

        for i in range(level - 1):
            try:
                vote = vote_dict[vote["vote_reduced"][0]]
            except KeyError:
                return vote

        return vote



    def update_vote_by_name(self, vote, vote_dict):
        """Update votes in place by comparing votes to usernames. Covers 
        extensible cases eg. 
        [X] Muramasa
        [X] Apply hugs to Ugo

        Returns True if vote was modified"""
        mod = False
        t = 0

        for n, line in enumerate(list(reversed(vote['vote_reduced']))):
            try:
                target = self.normalize_by_name(line, vote_dict)
            except KeyError:
                pass
            else:
                if not t:
                    t = len(vote['vote_reduced'])

                for key in self.vote_fourple:
                    vote[key][t-n-1:t-n] = target[key]

                if not mod:
                    mod = True

        return mod


    def uniq_votes_by_name(self, vote_list):
        """Removes duplicate votes by the same user. Takes list, returns an
        list. Additionally updates votes by username referral, direction
        based on the refer_dir parameter."""
        uniqed_votes = LUOrderedDict()

        for vote in vote_list:

            if self.refer_dir:
                self.update_vote_by_name(vote, uniqed_votes)

            uniqed_votes[vote["voters_reduced"][0]] = vote

        for vote in list(uniqed_votes.values()):
            # update_vote_by_name updates in place
            if self.update_vote_by_name(vote, uniqed_votes):
                uniqed_votes[vote["voters_reduced"][0]] = vote

        return uniqed_votes.values()


    def merge_votes_by_content(self, vote_list):
        """Merge votes by vote_reduced"""
        output = LUOrderedDict()

        for vote in vote_list:
            reduced_joined = ''.join(vote['vote_reduced'])
            try:
                target = output[reduced_joined]
            except KeyError:
                output[reduced_joined] = vote
            else:
                target["voters"] += vote["voters"]
                target["voters_reduced"] += vote["voters_reduced"]
                target["voters_full"] += vote["voters_full"]

        return output.values()


    def break_blocks(self, vote):
        """Generator, yields blocks from vote based on indentation level as a
        tuple vote_bbcode, vote_plain, vote_reduced, marker"""
        start = indent = prev = 0
        vote_bbcode, vote_plain, vote_reduced, marker = [], [], [], []

        for n, mark in enumerate(vote["marker"]):
            indent = len(mark.group(1)) - 1
            if prev != 0 and indent == 0:
                yield tuple(vote[key][start:n] for key in self.vote_fourple)
                start = n
            prev = indent

        yield tuple(vote[key][start:] for key in self.vote_fourple)


    def break_lines(self, vote):
        """Generator, yields lines from vote as a tuple vote_bbcode, vote_plain,
        vote_reduced, marker"""
        gen = zip(*(vote[k] for k in self.vote_fourple))
        for i in gen:
            yield tuple([j] for j in i)


    # def break_runoff(self, vote):
    #     """Breaks votes according to instant runoff directive"""
    #     prev = vote['marker'][0].group(1)

    #     for n, mark in enumerate(vote['marker']):
    #         curr = mark.group(1)
    #         if curr != prev:
    #             yield tuple(vote[key][start:n] for key in self.vote_fourple)
    #             start = n

    #         prev = curr
            
    #     yield tuple(vote[key][start:] for key in self.vote_fourple)


    def break_votes(self, vote_list):
        """Breaks votes based on the break_generator, set via settings
        1 = breaks into blocks based on subvotes denoted by indentation level
        2 = breaks into individual lines
        3 = instant runoff
        """
        output = deque()

        for vote in vote_list:
            for subvote in self.break_generator(vote):
                new_vote = vote.copy()
                for key, v in zip(self.vote_fourple, subvote):
                    new_vote[key] = v
                output.append(new_vote)

        return output


    # def order_votes_by_runoff(self, vote_list):
    #     """Builds a dictionary of dictionary of lists of votes. First layer
    #     is keyed by the grouping directive and second layer is keyed by
    #     numerical ranking."""
    #     vote_dict = LUOrderedDict()
    #     vote_list = self.break_votes(vote_list)

    #     # Aggregate by 
    #     for vote in vote_list:
    #         try:
    #             alphamark = vote['marker'][0].group(1)
    #             vote_dict[alphamark].append(vote)
    #         except KeyError:
    #             vote_dict[alphamark] = deque([vote])

    #     return vote_dict


    # def tally_vote_block(self, number_dict):
    #     """Tallies instant runoff voting block."""
    #     for number_mark, vote_list in number_dict.items():
    #         threshold = len(vote_list)/2

    #         vote_list = self.merge_votes_by_content(vote_list)

    #         highest = max(vote_list, key=lambda x: len(x['voters']))

    #         if len(highest['voters']) > threshold:
    #             return highest


    # def merge_votes_by_runoff(self, vote_list):
    #     """Merges votes according to the instant runoff voting method. Expects
    #     votes of the format [A][1], where A is an alphabetical grouping 
    #     directive and 1 is the numerical ranking."""
    #     self.break_generator = self.break_runoff

    #     vote_dict = self.order_votes_by_runoff(vote_list)

    #     for alphamark, vote_deque in vote_dict.items():
    #         alpha_vote_dict = LUOrderedDict()
    #         num = ""

    #         for v in vote_deque.items():
    #             if not num:
    #                 num = v['vote_marker'].groups(2)

                
    #             key = "".join( for m in v['vote_marker'] if m == num)


    def final_format(self, vote_list):
        if self.sort_highest:
            vote_list.sort(key=lambda x: len(x['voters']), reverse=True)
        for vote in vote_list:
            voters = ', '.join(
                self.voter_format.format(pid, un)
                for un, pid in vote['voters_full']
            )
            vote['repr'] = self.vote_format.format(
                self.BBparse.reconstruct(chain(*vote['vote_bbcode'])),
                len(vote['voters']),
                voters
            )

        return "\n\n".join(vote['repr'] for vote in vote_list)


    def pprint(self, vote_list):
        """Helper function to print vote lists"""
        for vote in vote_list:
            for k, v in vote.items():
                print(k, " : ", v)
            print()


    def tally_votes(self, post_list, op, **kwargs):
        """Tallies vote"""
        self.settings(**kwargs)

        vote_list = self.extract_votes(post_list)

        vote_list = self.uniq_votes_by_name(vote_list)

        if not self.instant_runoff:
            if self.break_level:
                vote_list = self.break_votes(vote_list)
            vote_list = self.merge_votes_by_content(vote_list)

        else:
            vote_list = self.merge_votes_by_runoff(vote_list)

        return self.final_format(vote_list)


    def _handle_timeout(self, signum, frame):
        raise TimeoutError("Tally timed out!")


    def tally_votes_timeout(self, post_list, op, **kwargs):
        signal.signal(signal.SIGALRM, self._handle_timeout)
        signal.alarm(10)
        try:
            result = self.tally_votes(post_list, op, **kwargs)
        finally:
            signal.alarm(0)

        return result
                


if __name__ == "__main__":
    from textwrap import dedent

    parse_text = dedent("""\
    [font=\"Tahoma\"][i]absbdasd[color=green]
    [x] vote1
    -- [b][x] vote[/color]
    [b]test1
    [i]test2[/i][/b]kjahsd[color='red']kash[/color][x] vot that wont be picked up!

    of course, lots of dissertation

    more dissertation and
    [QUOTE="'Lement, post: 4046370, member: 4959"][X] this is a vote
    --[b][x] subvote[/b][/font]
    - [color=red][x] another subvote[/color]
    [QUOTE]state.[/QUOTE][/QUOTE]kasjdh[list][/b]aoishdu912
    [x] stooopid
    """)

    test_vote_list = {
        'op' : 'Firnagzen',
        'posts' : [
            {
              'username':"A", 'user_id':"100", 'post_id':"1", 
              'message': dedent("""\
                [X] vote A-11
                -[X][b]subvote A-11[/b]
                [X] vote A-12
                ---[X]subvote A-22
                """)
            }, {
              'username':"B", 'user_id':"102", 'post_id':"2", 
              'message': dedent("""\
                [QUOTE="A, post: 1, member: 100"]
                [X] vote A-11
                -[X][b]subvote A-11[/b]
                [X] vote A-12
                ---[X]subvote A-22
                [/QUOTE]
                I disagree, because...
                """)
            }, {
              'username':"A", 'user_id':"101", 'post_id':"3", 
              'message': dedent("""\
                How's this?
                [X] vote A-21
                -[X][b]subvote A-21[/b]
                [X] vote A-22
                ---[X]subvote A-22
                """)
            }, {
              'username':"C", 'user_id':"103", 'post_id':"4", 
              'message': dedent("""\
                [color=red]Looks good to me.[/color]
                [X]A
                """)
            }, {
              'username':"D", 'user_id':"104", 'post_id':"5", 
              'message': dedent("""\

                [X] vote A-21
                -[X][b]subvote A-21[/b]
                [X] vote A-22
                ---[X]subvote A-22
                """)
            }, {
              'username':"A", 'user_id':"101", 'post_id':"6", 
              'message': dedent("""\
                [X] vote A-31
                -[X][b]subvote A-31[/b]
                [X] vote A-32
                ---[X]subvote A-32
                """)
            }, {
              'username':"E", 'user_id':"105", 'post_id':"7", 
              'message': dedent("""\
                [X] C
                """)
            }, {
              'username':"F", 'user_id':"106", 'post_id':"8", 
              'message': dedent("""\
                [X] A
                """)
            }, {
              'username':"G", 'user_id':"107", 'post_id':"9", 
              'message': dedent("""\
                [X] vote D-11
                -[X][b]subvote D-11[/b]
                """)
            }, {
              'username':"H", 'user_id':"108", 'post_id':"10", 
              'message': dedent("""\
                [X] G
                - [X] plus stuff
                """)
            }, {
              'username':"I", 'user_id':"109", 'post_id':"11", 
              'message': dedent("""\
                [spoiler]
                [X] A[/spoiler]
                """)
            }
        ]
    }

    BC = BBCodeParser()
    VC = VoteContainer()

    # ppost = BC.parse_tags(parse_text)

    # b = VC.tally_votes(test_vote_list, break_level = 2)
    # print(b)

    import timeit, json

    # with open('test.json', 'w') as f:
    #     f.write(json.dumps(test_vote_list))

    "thread_of_strife.json"
    with open("pmas.json", "r") as f:
        big_test = json.loads(f.read())

    # print(len(big_test['posts']))

    # import cProfile
    # p = cProfile.run(
    #     "[BC.parse_tags(i['message']) for i in big_test['posts']]", 
    #     sort = 'cumulative')

    # "[VC.tally_votes(test_vote_list) for i in range(10000)]"
    # "[VC.vote_from_text(parse_text) for i in range(10000)]"
    # "[BC.line_extract(ppost, VC.is_vote) for i in range(10000)]"

    # n = 10
    # a = timeit.timeit("VC.tally_votes(big_test['posts'])", setup=dedent("""
    # from __main__ import BBCodeParser, VoteContainer, big_test
    # VC = VoteContainer()"""), number = n)
    # print(a/n)

    # from line_profiler import LineProfiler
    # profiler = LineProfiler(
    #     VC.BBparse.parse_tags, VC.extract_votes, VC.vote_from_text, 
    #     VC.BBparse.index_tag_pairs, VC.BBparse.line_extract
    #     )
    # # profiler.add_function(func)
    # profiler.enable_by_count()

    b = VC.tally_votes_timeout(big_test['posts'], 'Firnagzen')

    # profiler.print_stats()

    # with open("result.dmp", 'r') as f:
    #     print(b == f.read())

