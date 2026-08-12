const API_BASE_URLS = {
  develop: 'https://finance-news-assistant-production.up.railway.app',
  trial: 'https://finance-news-assistant-production.up.railway.app',
  release: 'https://finance-news-assistant-production.up.railway.app'
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
