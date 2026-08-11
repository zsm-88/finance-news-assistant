const { AI_REQUEST_TIMEOUT, API_BASE_URL, REQUEST_TIMEOUT } = require('../config')

function request(path, data = {}, method = 'GET', timeout = REQUEST_TIMEOUT) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE_URL}${path}`,
      method,
      data,
      timeout,
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data)
          return
        }
        const detail = response.data && typeof response.data.detail === 'string'
          ? response.data.detail
          : `HTTP ${response.statusCode}`
        const error = new Error(detail)
        error.statusCode = response.statusCode
        reject(error)
      },
      fail(error) {
        const message = error && error.errMsg ? error.errMsg : 'NETWORK_ERROR'
        const requestError = new Error(message)
        requestError.code = /timeout/i.test(message) ? 'TIMEOUT' : 'NETWORK_ERROR'
        reject(requestError)
      }
    })
  })
}

function getDashboard() {
  return request('/api/v1/wechat/dashboard')
}

function getNews(params) {
  return request('/api/v1/wechat/news', params)
}

function getNewsDetail(id) {
  return request(`/api/v1/wechat/news/${encodeURIComponent(id)}`)
}

function getMarket() {
  return request('/api/v1/wechat/market')
}

function getMarketDetail(symbol) {
  return request(`/api/v1/wechat/market/${encodeURIComponent(symbol)}`)
}

function getMarketHistory(symbol, period = 'day', range = '1m') {
  return request(`/api/v1/wechat/market/${encodeURIComponent(symbol)}/history`, { period, range })
}

function searchFunds(query, refresh = false) {
  return request('/api/v1/wechat/funds/search', { q: query, refresh })
}

function getFundWatchlist(refresh = false) {
  return request('/api/v1/wechat/funds/watchlist', { refresh })
}

function getFundDetail(code, refresh = false) {
  return request(`/api/v1/wechat/funds/${encodeURIComponent(code)}`, { refresh })
}

function getFundNavHistory(code, range = '3m', refresh = false) {
  return request(`/api/v1/wechat/funds/${encodeURIComponent(code)}/nav-history`, { range, refresh })
}

function addFundWatchlist(code) {
  return request(`/api/v1/wechat/funds/watchlist/${encodeURIComponent(code)}`, {}, 'POST')
}

function removeFundWatchlist(code) {
  return request(`/api/v1/wechat/funds/watchlist/${encodeURIComponent(code)}`, {}, 'DELETE')
}

function saveFundPosition(code, value) {
  return request(`/api/v1/wechat/funds/positions/${encodeURIComponent(code)}`, value, 'PUT')
}

function removeFundPosition(code) {
  return request(`/api/v1/wechat/funds/positions/${encodeURIComponent(code)}`, {}, 'DELETE')
}

function chatWithAI(message, conversation = []) {
  return request('/api/v1/wechat/ai/chat', { message, conversation }, 'POST', AI_REQUEST_TIMEOUT)
}

module.exports = {
  getDashboard,
  getNews,
  getNewsDetail,
  getMarket,
  getMarketDetail,
  getMarketHistory,
  searchFunds,
  getFundWatchlist,
  getFundDetail,
  getFundNavHistory,
  addFundWatchlist,
  removeFundWatchlist,
  saveFundPosition,
  removeFundPosition,
  chatWithAI
}
