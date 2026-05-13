import logging
logging.basicConfig(filename='activity.log', level=logging.INFO)
def track_interaction(user_id, action):
  logging.info(f'User {user_id} performed action {action}')