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
    def __init__(self, timeout=10):
        self.defaults = {
            "sim_cutoff"         : 0.95,
            "break_level"        : 0, # 0=entire vote, 1=blocks, 2=lines
            "refer_dir"          : 0, # 0=both, 1=up then both
            "vote_marker"        : "\[[Xx✅✓✓]\]", #regex
            "instant_runoff"     : 0,
            "sort_highest"       : 0
        }

        self.timeout = timeout

        self.BBparse = BBCodeParser()

        self.rd = str.maketrans(
            ascii_uppercase, ascii_lowercase, 
            punctuation + whitespace)

        self.vote_format = "{}\n[b]No. of voters: {}[/b]\n{}"
        self.voter_format = "[post={}]{}[/post]"

        self.rem_text = set(["quote", "spoiler", "s"])

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
        ppost, bbc_i, newline_i = self.BBparse.parse_tags(post)
        
        rem = self.BBparse.find_breakpoints(bbc_i, newline_i, self.rem_text)

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


    def uniq_votes_by_name(self, vote_list, op=""):
        """Removes duplicate votes by the same user. Takes list, returns an
        list. Additionally updates votes by username referral, direction
        based on the refer_dir parameter."""
        uniqed_votes = LUOrderedDict()

        for vote in vote_list:
            if vote['voters'][0] == op:
                continue

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

        vote_list = self.uniq_votes_by_name(vote_list, op=op.lower())

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
        signal.alarm(self.timeout)
        try:
            result = self.tally_votes(post_list, op, **kwargs)
        finally:
            signal.alarm(0)

        return result
                


