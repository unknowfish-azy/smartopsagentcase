<template>
  <div class="detail-page">
    <ServerDetailHeader
        :server="server"
        :loading="loading"
        @back="goBack"
        @refresh="loadData"
    />

    <ServerInfoCard :server="server" />

    <ServerMetricOverview
        :metric="metric"
        :tag-type="metricTagType"
        :status-text="metricStatusText"
        :time-text="metricTimeText"
    />

    <ServerNetworkCard :metric="metric" />

    <ServerMetricHistory
        :metrics="metrics"
        :loading="metricsLoading"
        @refresh="loadMetrics"
    />
  </div>
</template>

<script setup>
import { useServerDetail } from '../../composables/useServerDetail.js'
import ServerDetailHeader from '../../components/server/detail/ServerDetailHeader.vue'
import ServerInfoCard from '../../components/server/detail/ServerInfoCard.vue'
import ServerMetricOverview from '../../components/server/detail/ServerMetricOverview.vue'
import ServerNetworkCard from '../../components/server/detail/ServerNetworkCard.vue'
import ServerMetricHistory from '../../components/server/detail/ServerMetricHistory.vue'

const {
  server,
  metric,
  metrics,
  loading,
  metricsLoading,
  metricTagType,
  metricStatusText,
  metricTimeText,
  loadData,
  loadMetrics,
  goBack
} = useServerDetail()
</script>

<style scoped>
.detail-page {
  width: 100%;
}
</style>
