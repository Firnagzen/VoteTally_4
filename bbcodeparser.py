import re
from operator import itemgetter
from bisect import bisect_left, bisect_right
from collections import namedtuple, Counter, deque
from itertools import chain, zip_longest, islice, compress

class TagSoup(object):
    def __init__(self, bbc_rep, bbc):
        self.bbc_rep        = bbc_rep
        self.bbc_indices    = bbc[0]
        self.newline_pos    = list(bbc[1])

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


    def skip_slice(self, lst, start, stop, skip):
        """Returns a slice of list lst from start to stop, skipping indices in
        skip"""
        start = start if start else 0
        stop = stop if stop else len(lst)
        indices = [i for i in skip if start <= i < stop]

        ranges = [[start]]
        for i in indices:
            ranges[-1].append(i)
            ranges.append([i + 1])
        ranges[-1].append(stop)

        try:
            getter = itemgetter(*[j for s, e in ranges for j in range(s, e)])
        except TypeError:
            return []

        return getter(lst)

        # return list(chain.from_iterable(islice(lst, s, e) for s, e in ranges))


    def get_lines(self):
        bbslice, plainslice = self[:]

        # Early exit
        if not self.bbc_all_il:
            return bbslice, "".join(plainslice)

        #Slice the regular bbcode by positions
        ns = list(zip([0]+self.newline_pos, self.newline_pos + [None]))
        bblines = [bbslice[i:j] for i, j in ns]

        #Shift the newline indices by bbcode positions
        count, nnewlines, curr_bbi = 0, [[0]], self.bbc_all_il[0]
        le = len(self.bbc_all_il)

        for i in self.newline_pos:
            while count < le and i > curr_bbi:
                count += 1
                try:
                    curr_bbi = self.bbc_all_il[count]
                except IndexError:
                    pass

            nnewlines[-1].append(i - count)
            nnewlines.append([i + 1 - count])
        nnewlines[-1].append(None)

        #Slice the plaintext by positions
        plainlines = ["".join(plainslice[i:j]) for i, j in nnewlines]

        return bblines, plainlines


    def find_slice_pos(self, rem_o, rem_c):
        rem_a = deque()
        level, prev_level = 0, 0
        lenght = max(len(rem_o), len(rem_c))
        o, c = rem_o.popleft(), rem_c.popleft()

        while True:
            if o < c:
                # Rising edge
                prev_level, level = level, level + 1

                # Detect step from baseline
                if prev_level == 0 and level == 1:
                    start = o

                try:
                    o = rem_o.popleft()
                except IndexError:
                    o = float('inf')

            else:
                # Falling edge
                prev_level, level = level, max(0, level - 1)

                # Detect step to baseline
                if prev_level == 1 and level == 0:
                    rem_a.append((start, c))

                try:
                    c = rem_c.popleft()
                except IndexError:
                    break

        return rem_a


    def normalize_newlines(self, rem_a):
        # Remove positions and normalize others
        count, new_new = 0, deque()
        rem_i = iter(rem_a)
        lower, upper = next(rem_i)

        for i in self.newline_pos:
            while i >= upper:
                count += upper - lower + 1
                try:
                    lower, upper = next(rem_i)
                except StopIteration:
                    upper = lower = float('inf')

            if i < lower:
                new_new.append(i - count)

        self.newline_pos = list(new_new)


    def normalize_bbcode_index(self, rem_a):
        # List out positions
        f = itemgetter(2)
        bbc = sorted(
            ((k, oc, i)                          # Key, open or close, index
            for k, l in self.bbc_indices.items() # Expand dictionary
            for oc, sl in enumerate(l)           # Open and close lists
            for i in sl),                        # Indexes
            key = f)

        # Remove positions and normalize others
        count, new_il = 0, dict()
        rem_i = iter(rem_a)
        lower, upper = next(rem_i)

        for k, oc, i in bbc:
            while i >= upper:
                count += upper - lower + 1
                try:
                    lower, upper = next(rem_i)
                except StopIteration:
                    upper = lower = float('inf')

            if i < lower:
                try:
                    new_il[k][oc].append(i - count)
                except KeyError:
                    new_il[k] = deque(), deque()
                    new_il[k][oc].append(i - count)

        # Reset values
        self.bbc_indices = new_il
        self.bbc_all_is  = {y for v in new_il.values() for x in v for y in x}
        self.bbc_all_il  = sorted(self.bbc_all_is)


    def remove_sections(self, tags):
        tags = [i for i in tags if i in self.bbc_indices]
        rem_o = deque(sorted(i for r in tags for i in self.bbc_indices[r][0]))
        rem_c = deque(sorted(i for r in tags for i in self.bbc_indices[r][1]))

        # Determine slicing positions
        if rem_o and rem_c:
            rem_a = self.find_slice_pos(rem_o, rem_c)
        else:
            # Early exit
            return

        # Slice out portions from bbcode representation
        for i, j in reversed(rem_a):
            del self.bbc_rep[i:j+1]

        # Normalize newline indices around removed segments
        self.normalize_newlines(rem_a)

        # Normalize bbcode indices around removed segments
        self.normalize_bbcode_index(rem_a)



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

        Returns a TagSoup object.
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

        return TagSoup(list(outer), (positions, newline_pos))


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


    def line_extract(self, target, condition, ignore_list=[]):
        """Expects a list as produced by parse_tags, extracts lines that fulfill
        condition, including all relevant BBCode, opens the tags. Returns two
        lists of lists of complete lines. One is parsed BBCode, the other is
        plaintext.

        Can be fed a list of position pairs to ignore."""
        tsave = target.bbc_rep[:], target.bbc_indices.copy(), target.newline_pos[:]
        target.remove_sections(ignore_list)

        # Get individual lines
        lines, plain_lines = target.get_lines()

        # Test lines
        gen = ((l, pl) for l, pl in zip(lines, plain_lines) if condition(pl))
        try:
            lines, plain_lines = list(list(i) for i in zip(*gen))
        except ValueError:
            return [], []

        # try:
        #     lines[0].insert(0, self.open_all_closed(chain(*lines),target[s::-1]))
        # except AttributeError:
        #     print(lines)
        #     print(plain_lines)
        #     raise AttributeError

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