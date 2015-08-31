import json, falcon
import voteparser
 
class TallyApp(object):
    def __init__(self):
        self.VC = voteparser.VoteContainer()


    def load_config(self):
        pass
        # Use dict update to udate dict from config?


    def on_get(self, req, resp):
        """Handles GET requests"""
        resp.status = falcon.HTTP_200
        resp.body = 'Vote tally active'
 

    def on_post(self, req, resp):
        """Handles POST requests"""
        try:
            raw_json = req.stream.read().decode()
        except Exception as ex:
            raise falcon.HTTPError(falcon.HTTP_400,
                'Error',
                ex.message)
 
        try:
            result_json = json.loads(raw_json, encoding='utf-8')
        except ValueError:
            raise falcon.HTTPError(falcon.HTTP_400,
                'Malformed JSON',
                'Could not decode the request body. The '
                'JSON was incorrect.')

        args = result_json['config'] if 'config' in result_json else dict()
        posts = result_json['posts']
        op = result_json['op']

        try:
            result = self.VC.tally_votes_timeout(posts, op, **args)
        except voteparser.TimeoutError:
            raise falcon.HTTPError(falcon.HTTP_400, "Operation timed out.")
        else:
            resp.status = falcon.HTTP_202
            resp.body = json.dumps(result)
 

wsgi_app = api = falcon.API()
app = TallyApp()
api.add_route('/tally', app)

# source venv/bin/activate
# gunicorn main:api
# http://localhost:8000/tally


# {
#      'op'   : <str>,
#      'posts': [
#                   {
#                       'username'        : <string>,
#                       'user_id'         : <int>,
#                       'message'         : <string>,
#                       'post_id'         : <int>
#                   },
#                   {
#                       ...
#                   }
#      ],
#      'config' : {
#                    "sim_cutoff"         : <int 1-99>,
#                    "break_level"        : <int 0-2>
#                    "refer_dir"          : <int 0-1>,
#                    "vote_marker"        : <str "\[[Xx]\]">,
#                    "instant_runoff"     : <int 0-1>,
#                    "sort_highest"       : <int 0-1>
#                }
# }