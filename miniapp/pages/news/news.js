const api = require('../../services/api')
const { presentNews } = require('../../utils/format')

const PAGE_SIZE = 20
const CATEGORIES = [
  { key: 'all', label: '全部', values: [] },
  { key: 'macro', label: '宏观' },
  { key: 'market', label: '市场' },
  { key: 'company', label: '公司' },
  { key: 'international', label: '国际' }
]

const CATEGORY_KEYWORDS = {
  macro: ['macro', 'policy', '宏观', '政策', '通胀', 'cpi', 'ppi', '经济数据'],
  market: ['market', 'commodity', 'forex', '市场', '商品', '外汇', '贵金属'],
  company: ['company', '公司', '企业', '业绩'],
  international: ['geopolitics', 'international', '国际', '海外', '地缘']
}

function categoryMatches(value, key) {
  const category = String(value || '').trim().toLowerCase()
  return (CATEGORY_KEYWORDS[key] || []).some((keyword) => category.includes(keyword))
}

Page({
  data: {
    status: 'loading',
    allItems: [],
    items: [],
    categories: CATEGORIES,
    selectedCategory: 'all',
    page: 1,
    hasMore: false,
    loadingMore: false
  },

  onLoad() { this.loadNews(true) },
  onPullDownRefresh() { this.loadNews(true, true) },
  onReachBottom() {
    if (this.data.hasMore && !this.data.loadingMore) this.loadNews(false)
  },
  retry() { this.loadNews(true) },

  selectCategory(event) {
    const selectedCategory = event.currentTarget.dataset.key
    this.setData({ selectedCategory })
    this.applyCategory(this.data.allItems, selectedCategory)
  },

  applyCategory(allItems, selectedCategory) {
    const category = CATEGORIES.find((item) => item.key === selectedCategory) || CATEGORIES[0]
    const items = category.key === 'all'
      ? allItems
      : allItems.filter((item) => categoryMatches(item.category, category.key))
    this.setData({ status: items.length ? 'success' : 'empty', items })
  },

  async loadNews(reset = true, fromRefresh = false) {
    const page = reset ? 1 : this.data.page + 1
    if (reset && !fromRefresh) this.setData({ status: 'loading' })
    if (!reset) this.setData({ loadingMore: true })
    try {
      const result = await api.getNews({ page, page_size: PAGE_SIZE })
      const incoming = (result.items || []).map(presentNews)
      const allItems = reset ? incoming : this.data.allItems.concat(incoming)
      this.setData({ allItems, page, hasMore: Boolean(result.has_more) })
      this.applyCategory(allItems, this.data.selectedCategory)
    } catch (error) {
      if (reset) this.setData({ status: 'error' })
      else wx.showToast({ title: '加载失败，请稍后重试', icon: 'none' })
    } finally {
      this.setData({ loadingMore: false })
      if (fromRefresh) wx.stopPullDownRefresh()
    }
  },

  openNews(event) {
    wx.navigateTo({ url: `/pages/news-detail/news-detail?id=${event.currentTarget.dataset.id}` })
  }
})

module.exports = { categoryMatches }
