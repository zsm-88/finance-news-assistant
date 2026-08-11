const api = require('../../services/api')
const {
  formatConfidence,
  formatDate,
  localizeAsset,
  localizeCategory,
  localizeDirection,
  presentNews,
  stars
} = require('../../utils/format')

Page({
  data: {
    id: '',
    status: 'loading',
    detail: null
  },

  onLoad(options) {
    if (!options.id) {
      this.setData({ status: 'error' })
      return
    }
    this.setData({ id: options.id })
    this.loadDetail()
  },

  async loadDetail() {
    this.setData({ status: 'loading' })
    try {
      const result = await api.getNewsDetail(this.data.id)
      const analysis = result.analysis
        ? {
          ...result.analysis,
          categoryText: localizeCategory(result.analysis.category),
          confidenceText: formatConfidence(result.analysis.confidence)
        }
        : null
      this.setData({
        status: 'success',
        detail: {
          ...result,
          coreSummary: result.summary || (analysis && analysis.summary) || '',
          analysisBody: analysis && analysis.summary !== result.summary ? analysis.summary : '',
          publishedAtText: formatDate(result.published_at),
          importanceText: stars(result.importance),
          categoryText: localizeCategory(result.category),
          analysis,
          market_impacts: (result.market_impacts || []).map((impact) => ({
            ...impact,
            assetText: localizeAsset(impact.asset),
            directionText: localizeDirection(impact.direction),
            confidenceText: formatConfidence(impact.confidence)
          })),
          related_news: (result.related_news || []).map(presentNews)
        }
      })
    } catch (error) {
      this.setData({ status: 'error' })
    }
  },

  openRelated(event) {
    wx.redirectTo({ url: `/pages/news-detail/news-detail?id=${event.currentTarget.dataset.id}` })
  },

  openSource() {
    const url = this.data.detail && this.data.detail.url
    if (!url) return
    wx.setClipboardData({
      data: url,
      success() {
        wx.showToast({ title: '原文链接已复制', icon: 'none' })
      }
    })
  }
})
