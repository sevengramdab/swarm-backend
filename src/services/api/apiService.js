const axios = require('axios');

module.exports = {
  fetchUser(user_id) {
    return axios.get(`https://api.example.com/user/${user_id}`);
  }
};