const { bounds, normalizeMarketPoints, normalizeNavPoints } = require('../../utils/chart')

const COLORS = {
  grid: '#203047',
  text: '#738198',
  rise: '#ff626b',
  fall: '#2dd4a0',
  line: '#30c7e8',
  ma5: '#e9b75b',
  ma10: '#ad8cff',
  ma20: '#4dd6c8',
  ma60: '#8a97aa'
}

Component({
  data: {
    tooltip: null
  },

  properties: {
    mode: { type: String, value: 'candlestick' },
    points: { type: Array, value: [] },
    showVolume: { type: Boolean, value: false }
  },

  observers: {
    'mode,points,showVolume': function () {
      this.selectedIndex = null
      if (this.data.tooltip) this.setData({ tooltip: null })
      this.scheduleDraw()
    }
  },

  lifetimes: {
    attached() {
      this.scheduleDraw()
    }
  },

  methods: {
    scheduleDraw() {
      if (typeof wx === 'undefined' || !wx.nextTick) return
      wx.nextTick(() => this.draw())
    },

    draw() {
      this.createSelectorQuery()
        .select('#financeChart')
        .fields({ node: true, size: true, rect: true })
        .exec((result) => {
          if (!result || !result[0] || !result[0].node) return
          const { node, width, height } = result[0]
          this.chartMetrics = { width, height, left: result[0].left || 0 }
          const ratio = wx.getSystemInfoSync().pixelRatio || 1
          node.width = width * ratio
          node.height = height * ratio
          const context = node.getContext('2d')
          context.scale(ratio, ratio)
          context.clearRect(0, 0, width, height)
          if (this.properties.mode === 'nav') {
            this.drawLine(context, width, height, normalizeNavPoints(this.properties.points))
          } else {
            this.drawMarket(context, width, height, normalizeMarketPoints(this.properties.points))
          }
        })
    },

    drawGrid(context, width, top, bottom) {
      context.strokeStyle = COLORS.grid
      context.lineWidth = 1
      for (let index = 0; index <= 4; index += 1) {
        const y = top + ((bottom - top) * index) / 4
        context.beginPath()
        context.moveTo(48, y)
        context.lineTo(width - 10, y)
        context.stroke()
      }
    },

    drawMarket(context, width, height, points) {
      if (!points.length) return
      const top = 20
      const priceBottom = this.properties.showVolume ? height * 0.72 : height - 38
      const chartWidth = width - 66
      const priceBounds = bounds(points.flatMap((item) => [item.low, item.high, item.ma5, item.ma10, item.ma20, item.ma60]))
      if (!priceBounds) return
      this.drawGrid(context, width, top, priceBottom)
      this.drawScale(context, priceBounds, top, priceBottom)
      const x = (index) => 52 + (chartWidth * (index + 0.5)) / points.length
      const y = (value) => top + ((priceBounds.max - value) / (priceBounds.max - priceBounds.min)) * (priceBottom - top)
      if (this.properties.mode === 'line') {
        this.drawSeries(context, points, x, y, 'close', COLORS.line)
      } else {
        const candleWidth = Math.max(1, Math.min(8, (chartWidth / points.length) * 0.62))
        points.forEach((item, index) => {
          const color = item.close >= item.open ? COLORS.rise : COLORS.fall
          const center = x(index)
          context.strokeStyle = color
          context.fillStyle = color
          context.beginPath()
          context.moveTo(center, y(item.high))
          context.lineTo(center, y(item.low))
          context.stroke()
          const bodyTop = Math.min(y(item.open), y(item.close))
          const bodyHeight = Math.max(1, Math.abs(y(item.open) - y(item.close)))
          context.fillRect(center - candleWidth / 2, bodyTop, candleWidth, bodyHeight)
        })
      }
      this.drawSeries(context, points, x, y, 'ma5', COLORS.ma5)
      this.drawSeries(context, points, x, y, 'ma10', COLORS.ma10)
      this.drawSeries(context, points, x, y, 'ma20', COLORS.ma20)
      this.drawSeries(context, points, x, y, 'ma60', COLORS.ma60)
      if (this.properties.showVolume) this.drawVolume(context, width, height, points, x)
      this.drawDates(context, width, height, points)
      const selected = this.selectedIndex
      if (Number.isInteger(selected) && points[selected]) {
        this.drawCrosshair(context, x(selected), y(points[selected].close), top, priceBottom)
      }
    },

    drawLine(context, width, height, points) {
      if (!points.length) return
      const top = 20
      const bottom = height - 38
      const valueBounds = bounds(points.map((item) => item.value))
      if (!valueBounds) return
      this.drawGrid(context, width, top, bottom)
      this.drawScale(context, valueBounds, top, bottom)
      const x = (index) => 52 + ((width - 66) * index) / Math.max(1, points.length - 1)
      const y = (value) => top + ((valueBounds.max - value) / (valueBounds.max - valueBounds.min)) * (bottom - top)
      this.drawSeries(context, points, x, y, 'value', COLORS.line)
      this.drawDates(context, width, height, points)
      const selected = this.selectedIndex
      if (Number.isInteger(selected) && points[selected]) {
        this.drawCrosshair(context, x(selected), y(points[selected].value), top, bottom)
      }
    },

    drawSeries(context, points, x, y, field, color) {
      let started = false
      context.beginPath()
      context.strokeStyle = color
      context.lineWidth = field === 'close' || field === 'value' ? 2 : 1
      points.forEach((item, index) => {
        const value = item[field]
        if (!Number.isFinite(value)) {
          started = false
          return
        }
        if (!started) context.moveTo(x(index), y(value))
        else context.lineTo(x(index), y(value))
        started = true
      })
      context.stroke()
    },

    drawVolume(context, width, height, points, x) {
      const top = height * 0.78
      const bottom = height - 38
      const maxVolume = Math.max(...points.map((item) => item.volume || 0))
      if (!maxVolume) return
      const barWidth = Math.max(1, Math.min(7, ((width - 66) / points.length) * 0.6))
      points.forEach((item, index) => {
        const volume = item.volume || 0
        context.fillStyle = item.close >= item.open ? COLORS.rise : COLORS.fall
        const barHeight = ((bottom - top) * volume) / maxVolume
        context.fillRect(x(index) - barWidth / 2, bottom - barHeight, barWidth, barHeight)
      })
    },

    drawScale(context, valueBounds, top, bottom) {
      context.fillStyle = COLORS.text
      context.font = '10px sans-serif'
      context.textAlign = 'left'
      context.fillText(valueBounds.max.toFixed(2), 2, top + 8)
      context.fillText(valueBounds.min.toFixed(2), 2, bottom)
    },

    drawDates(context, width, height, points) {
      const first = String(points[0].timestamp).slice(0, 10)
      const last = String(points[points.length - 1].timestamp).slice(0, 10)
      context.fillStyle = COLORS.text
      context.font = '10px sans-serif'
      context.textAlign = 'left'
      context.fillText(first, 52, height - 8)
      context.textAlign = 'right'
      context.fillText(last, width - 10, height - 8)
    },

    drawCrosshair(context, x, y, top, bottom) {
      context.save()
      context.setLineDash([3, 3])
      context.strokeStyle = '#65748b'
      context.lineWidth = 1
      context.beginPath()
      context.moveTo(x, top)
      context.lineTo(x, bottom)
      context.moveTo(48, y)
      context.lineTo(this.chartMetrics.width - 10, y)
      context.stroke()
      context.setLineDash([])
      context.beginPath()
      context.arc(x, y, 3, 0, Math.PI * 2)
      context.fillStyle = COLORS.line
      context.fill()
      context.restore()
    },

    onTouchMove(event) {
      const metrics = this.chartMetrics
      const touch = event.touches && event.touches[0]
      if (!metrics || !touch) return
      const rawX = Number.isFinite(touch.x) ? touch.x : touch.clientX - metrics.left
      if (!Number.isFinite(rawX)) return
      const mode = this.properties.mode
      const points = mode === 'nav'
        ? normalizeNavPoints(this.properties.points)
        : normalizeMarketPoints(this.properties.points)
      if (!points.length) return
      const chartWidth = metrics.width - 66
      const rawIndex = mode === 'nav'
        ? Math.round(((rawX - 52) * Math.max(1, points.length - 1)) / chartWidth)
        : Math.round(((rawX - 52) * points.length) / chartWidth - 0.5)
      const index = Math.max(0, Math.min(points.length - 1, rawIndex))
      if (index === this.selectedIndex) return
      this.selectedIndex = index
      const point = points[index]
      const tooltip = mode === 'nav'
        ? {
            mode: 'nav',
            date: String(point.timestamp).slice(0, 10),
            value: this.numberText(point.value, 4)
          }
        : {
            mode: 'market',
            date: String(point.timestamp).slice(0, 10),
            open: this.numberText(point.open),
            high: this.numberText(point.high),
            low: this.numberText(point.low),
            close: this.numberText(point.close),
            volume: Number.isFinite(point.volume) ? Math.round(point.volume).toLocaleString() : '--'
          }
      this.setData({ tooltip })
      this.draw()
    },

    onTouchEnd() {
      this.selectedIndex = null
      this.setData({ tooltip: null })
      this.draw()
    },

    numberText(value, precision = 2) {
      return Number.isFinite(value) ? value.toFixed(precision) : '--'
    }
  }
})
