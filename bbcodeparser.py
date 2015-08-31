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

        outer = deque()

        # re.split produces text in groups of 7
        for t, full, close, name, _, value in chop:
            if t:
                outer.append(t)

            if full:
                try:
                    name = name.lower()
                except AttributeError:
                    outer.append(full)
                else:
                    # Validate BBCode
                    if name in self.valid_bbcode:
                        outer.append(self.Tag(full, close, name, value))
                    else:
                        outer.append(full)

        return list(outer)


    def index_tag_pairs(self, target, tags):
        """Expects a list as produced by parse_tags, returns largest possible 
        ranges wrapped by matching tags. Takes an iterable of tags."""
        tags = set(tags)
        output = deque()
        start, level, prev = 0, 0, 0

        # Find tag indices, position 0 for open and 1 for closed
        for n, tag in enumerate(target):
            if isinstance(tag, self.Tag) and tag.name in tags:
                level += -1 if tag.close else 1
                level = max(0, level)

                # Detect step from baseline
                if prev == 0 and level == 1:
                    start = n

                # Detect step to baseline
                elif prev == 1 and level == 0:
                    output.append((start, n))

                prev = level

        return list(output)


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


    def range_generator(self, ignore_ranges):
        "Gets next range from list of ranges. Yields infinity on finish."
        large =  9999999

        for i in ignore_ranges:
            yield i
        yield large, large


    def in_valid_range(self, flat_ignore_ranges, ind):
        "Checks if ind is inside ignore ranges"
        return not bisect.bisect(flat_ignore_ranges, ind) % 2


    def indices(self, lst, element):
        "Finds element in lst, returns lists of appendices."
        result = deque()
        offset = -1
        while True:
            try:
                offset = lst.index(element, offset+1)
            except ValueError:
                return result
            result.append(offset)

    def merge_ranges(self, ranges):
        "Merge adjacent and overlapping ranges."
        ranges = iter(sorted(ranges))
        current_start, current_stop = next(ranges)

        for start, stop in ranges:
            if start > current_stop:
                # Gap between segments: output current segment
                yield current_start, current_stop
                current_start, current_stop = start, stop

            else:
                # Segments adjacent or overlapping: merge.
                current_stop = max(current_stop, stop)
                
        yield current_start, current_stop


    def line_extract(self, target, condition, ignore_ranges=[]):
        """Expects a list as produced by parse_tags, extracts lines that fulfill
        condition, including all relevant BBCode, opens the tags. Returns two
        lists of lists of complete lines. One is parsed BBCode, the other is
        plaintext.

        Can be fed a list of position pairs to ignore."""
        s = -1        
        lines, plain_lines = deque(), deque()

        plain_rep = ""
        bbcode_rep = deque()

        range_gen = self.range_generator(ignore_ranges)
        lower, upper = next(range_gen)

        # Dividing the post by newlines, reconstruct lines and check condition
        for n, node in enumerate(target):
            # if newline, check the sentence and clear it.

            if node == '\n':
                if condition(plain_rep):
                    plain_lines.append(plain_rep)
                    lines.append(bbcode_rep)

                    # Record position to scan back from for open_all_closed
                    if s == -1:
                        s = n

                # clear line
                plain_rep = ""
                bbcode_rep = deque()

            # Check ignore ranges
            while n >= upper:
                lower, upper = next(range_gen)

            # Construct line
            if n < lower:
                bbcode_rep.append(node)
                try:
                    plain_rep += node
                except TypeError:
                    pass

        if not lines:
            return None, None

        lines[0].extendleft(self.open_all_closed(chain(*lines),target[s::-1]))
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