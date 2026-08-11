const API_BASE_URLS = {
  develop: 'http://192.168.0.109:8000',
  trial: 'https://api.example.com',
  release: 'https://api.example.com'
}

function getEnvironment() {
  try {
    return wx.getAccountInfoSync().miniProgram.envVersion || 'develop'
  } catch (error) {
    return 'develop'
  }
}

module.exports = {
  API_BASE_URL: API_BASE_URLS[getEnvironment()],
  REQUEST_TIMEOUT: 30000,
  AI_REQUEST_TIMEOUT: 70000
}
