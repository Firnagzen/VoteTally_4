from textwrap import dedent
from voteparser import VoteContainer
from bbcodeparser import BBCodeParser

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
#     "VC.tally_votes(big_test['posts'], 'Firnagzen')", 
#     sort = 'cumulative')

# "[VC.tally_votes(test_vote_list) for i in range(10000)]"
# "[VC.vote_from_text(parse_text) for i in range(10000)]"
# "[BC.line_extract(ppost, VC.is_vote) for i in range(10000)]"

# n = 10
# a = timeit.timeit("VC.tally_votes(big_test['posts'], 'Firnagzen')", setup=dedent("""
# from __main__ import BBCodeParser, VoteContainer, big_test
# VC = VoteContainer()"""), number = n)
# print(a/n)

# from line_profiler import LineProfiler
# profiler = LineProfiler(
#     VC.BBparse.parse_tags, VC.extract_votes, VC.vote_from_text, 
#     VC.BBparse.index_tag_pairs, VC.BBparse.line_extract
#     )
# profiler.add_function(func)
# profiler.enable_by_count()

b = VC.tally_votes(big_test['posts'], 'Firnagzen')
print(b)

# profiler.print_stats()

# with open("result.dmp", 'r') as f:
#     print(b == f.read())