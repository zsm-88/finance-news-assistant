const { normalizeMarketPoints } = require('../../utils/chart')

Component({
  options: {
    styleIsolation: 'apply-shared'
  },
  properties: {
    points: { type: Array, value: [] },
    direction: { type: String, value: 'flat' }
  },
  observers: {
    'points,direction': function () {
      if (typeof wx !== 'undefined' && wx.nextTick) wx.nextTick(() => this.draw())
    }
  },
  lifetimes: {
    attached() {
      if (typeof wx !== 'undefined' && wx.nextTick) wx.nextTick(() => this.draw())
    }
  },
  methods: {
    draw() {
      const points = normalizeMarketPoints(this.properties.points)
      if (points.length < 2) return
      this.createSelectorQuery().select('#miniTrend').fields({ node: true, size: true }).exec((result) => {
        if (!result || !result[0] || !result[0].node) return
        const { node, width, height } = result[0]
        const ratio = wx.getSystemInfoSync().pixelRatio || 1
        node.width = width * ratio
        node.height = height * ratio
        const context = node.getContext('2d')
        context.scale(ratio, ratio)
        context.clearRect(0, 0, width, height)
        const closes = points.map((item) => item.close)
        let min = Math.min(...closes)
        let max = Math.max(...closes)
        if (min === max) { min -= 1; max += 1 }
        const x = (index) => 4 + ((width - 8) * index) / (closes.length - 1)
        const y = (value) => 8 + ((max - value) / (max - min)) * (height - 16)
        context.beginPath()
        closes.forEach((value, index) => index ? context.lineTo(x(index), y(value)) : context.moveTo(x(index), y(value)))
        context.strokeStyle = this.properties.direction === 'rise' ? '#ff626b' : this.properties.direction === 'fall' ? '#2dd4a0' : '#738198'
        context.lineWidth = 2
        context.stroke()
      })
    }
  }
})
