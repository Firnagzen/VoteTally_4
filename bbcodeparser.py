import re
import bisect
from itertools import chain, zip_longest, islice
from collections import namedtuple, Counter, deque

class TagSoup(object):
    def __init__(self, bbc_rep, plain_rep, bbc=None):
        self.bbc_rep        = bbc_rep
        self.bbc_indices    = bbc[0]
        self.newline_pos    = bbc[1]

        self.bbc_all_is     = {y for v in bbc[0].values() for x in v for y in x}
        self.bbc_all_il     = sorted(self.bbc_all_is)


    def __getitem__(self, key):
        bbslice = self.bbc_rep[key]

        try:
            le = key.start
            lo = key.stop
        except AttributeError:
            plainslice = bbslice
        else:
            plainslice = self.skip_slice(self.bbc_rep, le, lo, self.bbc_all_il)

        return bbslice, plainslice


    def skip_slice(self, lst, start, stop):
        """Returns a slice of list lst from start to stop, skipping indices in
        self.bbc_all_il"""
        indices = [i for i in self.bbc_all_il if start <= i < stop]

        ranges = [[start]]
        for i in indices:
            ranges[-1].append(max(0, i-1))
            ranges.append([i + 1])
        ranges[-1].append(stop)

        return list(chain.from_iterable(islice(lst, s, e) for s, e in ranges))


    def get_lines(self, condition):
        bbslice, plainslice = self[:]

        #Slice the regular bbcode by positions
        ns = list(zip([0]+self.newline_pos, self.newline_pos+[None]))
        bblines = [bbslice[i:j] for i, j in ns]

        #Shift the newline indices by bbcode positions
        count, nnewlines, curr_bbi = 0, [], self.bbc_all_il[0]
        for i in self.newline_pos:
            if i > cur_bbi:
                count += 1
                curr_bbi = self.bbc_all_il[count]

            nnewlines.append(i - count)

        #Slice the plaintext by positions
        ns = list(zip([0]+nnewlines, nnewlines+[None]))
        plainlines = [plainslice[i:j] for i, j in ns]

        return bbslice, plainslice


    def remove_sections(self, tags):
        rem_o = deque(i for r in tags for i in self.bbc_indices[r][0])
        rem_c = deque(i for r in tags for i in self.bbc_indices[r][1])

        if rem_o and rem_c:
            rem_a = deque()
            level, prev_level = 1, 0
            o, c = rem_o.popleft(), rem_c.popleft()

            while True:
                # Detect step from baseline
                if prev == 0 and level == 1:
                    start = o

                # Detect step to baseline
                elif prev == 1 and level == 0:
                    rem_a.append((start, c))

                if o < c:
                    prev_level, level = level, level + 1
                    try:
                        o = rem_o.popleft()
                    except IndexError:
                        pass

                else:
                    prev_level, level = level, max(0, level - 1)
                    try:
                        c = rem_c.popleft()
                    except IndexError:
                        break

        for i, j in reversed(rem_a):
            del self.bbc_rep[i:j]


class BBCodeParser(object):
    def __init__(self):
        self.tag_re = re.compile(
            r"("                                   # -Capture tag entire
            r"\n\n*|"                              # Newline
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
        self.first = 0


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

        Additionally returns indexed lists of BBCode tag positions as a
        dictionary indexed by BBCode names of the form:
        {
            'name': [deque_of_open_tag_positions, deque_of_close_tag positions],
        }
        """
        chop = self.tag_re.split(target)
        chop = self.grouper(chop, 6)

        outer = deque()
        count = -1
        positions = dict()
        newline_pos = deque()

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

                else:
                    # Validate BBCode
                    if name in self.valid_bbcode:
                        outer.append(self.Tag(full, close, name, value))

                        # Build position index for fast BBCode access
                        try:
                            curr = positions[name]
                        except KeyError:
                            curr = positions[name] = [deque(), deque()]
                        finally:
                            curr[1 if close else 0].append(count)

                    else:
                        outer.append(full)
                        if '\n' in full:
                            newline_pos.append(count)

        return list(outer), (positions, newline_pos)


    def index_tag_pairs(self, bbindices, tags):
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

            if '\n' in node:
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