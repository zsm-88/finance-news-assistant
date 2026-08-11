Component({
  options: {
    styleIsolation: 'apply-shared'
  },
  properties: {
    status: { type: String, value: 'empty' },
    title: { type: String, value: '暂无数据' },
    description: { type: String, value: '' },
    actionText: { type: String, value: '' },
    compact: { type: Boolean, value: false }
  },
  methods: {
    onRetry() {
      this.triggerEvent('retry')
    }
  }
})
