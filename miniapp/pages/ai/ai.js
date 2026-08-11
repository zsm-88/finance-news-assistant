const api = require('../../services/api')

const QUICK_QUESTIONS = ['今日市场', '重要新闻', 'A股为什么涨？', '我的基金', '最近市场热点']
const INTENT_LABELS = {
  GENERAL_FINANCE: '财经问答',
  NEWS: '新闻分析',
  MARKET: '行情分析',
  FUND: '基金数据',
  NEWS_MARKET: '新闻与行情',
  MARKET_EVENT: '市场事件',
  FUND_ANALYSIS: '基金分析',
  UNKNOWN: '数据分析'
}

function dataTimeText(value) {
  const date = new Date(value)
  if (!value || Number.isNaN(date.getTime())) return '--'
  const shanghai = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  const pad = (number) => String(number).padStart(2, '0')
  return `${shanghai.getUTCFullYear()}-${pad(shanghai.getUTCMonth() + 1)}-${pad(shanghai.getUTCDate())} ${pad(shanghai.getUTCHours())}:${pad(shanghai.getUTCMinutes())}`
}

function presentResponse(value) {
  return {
    ...value,
    key_points: value.key_points || [],
    market_impacts: value.market_impacts || [],
    references: value.references || [],
    intentText: INTENT_LABELS[value.intent] || '数据分析',
    dataTimeText: dataTimeText(value.data_time),
    showDataStatus: value.data_status && value.data_status !== '数据正常'
  }
}

Page({
  data: {
    quickQuestions: QUICK_QUESTIONS,
    messages: [],
    inputValue: '',
    loading: false,
    errorMessage: '',
    lastQuestion: '',
    scrollTarget: ''
  },

  onInput(event) {
    this.setData({ inputValue: event.detail.value })
  },

  askQuickQuestion(event) {
    this.ask(event.currentTarget.dataset.question)
  },

  sendMessage() {
    this.ask(this.data.inputValue)
  },

  retry() {
    if (this.data.lastQuestion) this.ask(this.data.lastQuestion, true)
  },

  async ask(rawQuestion, retry = false) {
    const question = String(rawQuestion || '').trim()
    if (!question || this.data.loading) return
    const previous = this.data.messages
    const conversation = previous.slice(-5).map((item) => ({
      role: item.role,
      content: item.role === 'assistant' ? item.response.answer : item.content
    }))
    const userMessage = { id: `user-${Date.now()}`, role: 'user', content: question }
    const messages = retry ? previous : previous.concat(userMessage)
    this.setData({
      messages,
      inputValue: '',
      loading: true,
      errorMessage: '',
      lastQuestion: question,
      scrollTarget: 'assistant-loading'
    })
    try {
      const response = presentResponse(await api.chatWithAI(question, conversation))
      const assistantMessage = { id: `assistant-${Date.now()}`, role: 'assistant', response }
      this.setData({
        messages: messages.concat(assistantMessage),
        loading: false,
        scrollTarget: assistantMessage.id
      })
    } catch (error) {
      const unavailable = error && (error.statusCode === 502 || error.statusCode === 503)
      const timeout = error && error.code === 'TIMEOUT'
      this.setData({
        loading: false,
        errorMessage: unavailable
          ? 'AI 财经助手暂时不可用，请稍后重试'
          : timeout
            ? 'AI 分析超时，请重新提问'
            : '无法连接服务，请确认本地服务已启动后重试',
        scrollTarget: 'assistant-error'
      })
    }
  },

  openReference(event) {
    const { id, type } = event.currentTarget.dataset
    if (type === 'news') {
      wx.navigateTo({ url: `/pages/news-detail/news-detail?id=${encodeURIComponent(id)}` })
    } else if (type === 'market') {
      wx.navigateTo({ url: `/pages/market-detail/market-detail?symbol=${encodeURIComponent(id)}` })
    } else if (type === 'fund') {
      wx.navigateTo({ url: `/pages/fund-detail/fund-detail?code=${encodeURIComponent(id)}` })
    }
  }
})

module.exports = { dataTimeText, presentResponse }
