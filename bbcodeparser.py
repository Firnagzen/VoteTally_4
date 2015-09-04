import re
import bisect
from itertools import chain, zip_longest
from collections import namedtuple, Counter, deque

class BBCodeParser(object):
    def __init__(self):
        self.tag_re = re.compile(
            r"("                                   # -Capture tag entire
            r"\n|"                                 # Newline
            r"\["                                  # Opening square bracket
            r"(/)?"                                # -Capture the closing tag /
            r"([^]=]*)"                            # -Capture tag name
            r"(?:=(?P<quote>['\"]?)"               # -Capture opening quotation
            r"([^]]*)"                             # -Capture tag attribute
            r"(?P=quote))?"                        # Closing quotation match
            r"\])"                                 # Closing square bracket
        )

        self.Tag = namedtuple("Tag", ["full", "close", "name", "value"])

        self.valid_bbcode = set([
            "b", "i", "u", "s", "font", "color", "size", "url", "email", "user",
            "img", "media", "thread", "post", "list", "left", "right", "center",
            "quote", "code", "spoiler", "php", "html", "indent", "plain",
            "attach", "accordion", "article", "bimg", "encadre", "fieldset", 
            "fleft", "fright", "gview", "latex", "slider", "spoilerbb", "tabs", 
            "xtable"
        ])

    def grouper(self, iterable, n, fillvalue=None):
        args = [iter(iterable)] * n
        return zip_longest(*args, fillvalue=fillvalue)


    def parse_tags(self, target):
        """Parses BBCode string into a list containing text and tags using the
        Tag object.

        The Tag is a namedtuple comprising:
        -full, the full BBCode tag
        -close, a string containing either '/' or None
        -name, the name of the tag
        -value, the value of the tag.

        For example,
        Tag(full='[font="Tahoma"]', close=None, name='font', value='Tahoma')
        """
        chop = self.tag_re.split(target)
        chop = self.grouper(chop, 6)

        count = -1
        positions = dict()
        newline_pos, outer = deque(), deque()

        # re.split produces text in groups of 7
        for t, full, close, name, _, value in chop:
            if t:
                outer.append(t)
                count += 1

            if full:
                count += 1

                try:
                    name = name.lower()

                except AttributeError:
                    outer.append(full)
                    # Build newline index for fast access
                    if '\n' in full:
                        newline_pos.append(count)

                else:
                    # Validate BBCode
                    if name in self.valid_bbcode:
                        outer.append(self.Tag(full, close, name, value))

                        # Build position index for fast BBCode access
                        try:
                            curr = positions[name]
                        except KeyError:
                            curr = positions[name] = deque(), deque()
                        finally:
                            if close:
                                curr[1].append(count)
                            else:
                                curr[0].append(count)

                    else:
                        outer.append(full)
        return list(outer), positions, newline_pos


    def invert_ranges(self, ranges):
        "Merge adjacent and overlapping ranges, return inverted slicing ranges."
        previous_stop = 0
        ranges = iter(sorted(ranges))
        curr_start, curr_stop, cl = next(ranges)

        for start, stop, nl in ranges:
            if start > curr_stop + 1:
                # Gap between segments: output current segment
                yield previous_stop, curr_start, cl
                previous_stop = curr_stop + 1
                curr_start, curr_stop = start, stop

            else:
                # Segments adjacent or overlapping: merge.
                curr_stop = max(curr_stop, stop)

            # Newline marker
            cl = nl

        yield previous_stop, curr_start, nl
        yield curr_stop, None, 0


    def find_breakpoints(self, bbc_indices, nl_indices, rem):
        # Unpack bbcode indices as ranges for those that are to be removed
        rem_bbc =[
            (j, l, False) 
            for k, i in bbc_indices.items() 
            for j, l in zip(*i) 
            if k in rem
            ]

        # Unpack newline indices
        rem_bbc.extend((i, i, True) for i in nl_indices)

        # Make a copy for plaintext version
        rem_plain = rem_bbc.copy()

        # Unpack other bbcode indices as points
        rem_plain.extend(
            (l, l, False) 
            for k,i in bbc_indices.items() 
            for j in zip(*i)
            for l in j
            if k not in rem
            )

        print(rem_plain)

        return self.invert_ranges(rem_bbc), self.invert_ranges(rem_plain)


    def close_all_open(self, target):
        """Expects a list as produced by parse_tags, returns closures to all
        open tags"""
        # Count the number of open tags
        open_tags = Counter()
        for i in target:
            try:
                open_tags[i.name] += 1 if not i.close else -1
            except AttributeError:
                pass

        return [
            self.Tag("[/{}]".format(tag), "/", tag, None) 
            for tag in open_tags.elements()
            ]


    def open_all_closed(self, target, takefrom):
        """Expects a list as produced by parse_tags, returns closures to all
        open tags"""
        # Count up number of closed tags in extracted lines.
        closed_tags = Counter()
        
        for i in target:
            try:
                closed_tags[i.name] += 1 if i.close else -1
            except AttributeError:
                pass

        # Pypy doesn't support the +Counter operator yet
        try:
            closed_tags = +closed_tags
        except TypeError:
            closed_tags = Counter((k,v) for k,v in closed_tags.items() if v > 0)

        # Scan backwards, check for open tags matching to unmatched closed tags
        output = deque()
        if sum(closed_tags.values()):
            for tag in takefrom:
                try:
                    if closed_tags[tag.name] > 0 and not tag.close:
                        closed_tags[tag.name] -= 1
                        output.append(tag)

                        if not sum(closed_tags.values()):
                            break

                except AttributeError:
                    pass

        return output


    def line_extract(self, target, condition, ranges):
        """Expects a list as produced by parse_tags, extracts lines that fulfill
        condition, including all relevant BBCode, opens the tags. Returns two
        lists of lists of complete lines. One is parsed BBCode, the other is
        plaintext.

        Can be fed a list of position pairs to ignore."""
        print([target[i:j] for i, j, nl in ranges[0]])
        lines = [target[i:j] for i, j, nl in ranges[0]]
        print([target[i:j] for i, j, nl in ranges[1]])
        raise Exception
        plain_lines = ["".join(target[i:j]) for i, j in ranges[1]]

        if not lines:
            return None, None

        # lines[0].extendleft(self.open_all_closed(chain(*lines),target[s::-1]))
        # lines[-1].extend((self.close_all_open(chain(*lines))))

        return list(lines), list(plain_lines)


    def strip_bbcode(self, target):
        """Expects a list as produced by parse_tags, returns a string without
        BBCode"""
        return "".join(i for i in target if isinstance(i, str))


    def get_text(self, test):
        """Returns string if string, else returns full BBCode repr"""
        try:
            return test.full
        except AttributeError:
            return test

    def reconstruct(self, target):
        """Expects a list as produced by parse_tags, returns a string with 
        correct BBCode"""
        target = list(target)
        target += self.close_all_open(target)
        return "".join(self.get_text(i) for i in target).strip()