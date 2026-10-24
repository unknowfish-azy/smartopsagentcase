<template>
  <el-card
      class="stat-card"
      shadow="hover"
      :class="`stat-card-${type}`"
  >

    <div class="stat-card-content">

      <!-- 左侧图标 -->
      <div class="stat-icon">
        <el-icon :size="24">
          <component :is="icon" />
        </el-icon>
      </div>


      <!-- 中间数据 -->
      <div class="stat-main">

        <div class="stat-title">
          {{ title }}
        </div>

        <div class="stat-value">
          {{ displayValue }}
        </div>

        <div
            v-if="description"
            class="stat-description"
        >
          {{ description }}
        </div>

      </div>


      <!-- 右侧趋势 -->
      <div
          v-if="showTrend"
          class="stat-trend"
          :class="trendClass"
      >

        <el-icon>
          <component :is="trendIcon" />
        </el-icon>

        <span>
          {{ trendText }}
        </span>

      </div>

    </div>

  </el-card>
</template>


<script setup>

import {
  computed
} from 'vue'

import {
  ArrowUp,
  ArrowDown,
  Minus
} from '@element-plus/icons-vue'


/**
 * =========================================================
 * Props
 * =========================================================
 */

const props = defineProps({

  /**
   * 标题
   *
   * 例如：
   * 服务器总数
   */
  title: {
    type: String,
    required: true
  },


  /**
   * 数值
   *
   * 可以是：
   * 12
   * "12"
   * "92.3%"
   */
  value: {
    type: [String, Number],
    default: 0
  },


  /**
   * 图标
   *
   * 使用 Element Plus Icon
   */
  icon: {
    type: [Object, Function],
    default: null
  },


  /**
   * 卡片类型
   *
   * primary
   * success
   * warning
   * danger
   * info
   */
  type: {
    type: String,
    default: 'primary'
  },


  /**
   * 描述
   */
  description: {
    type: String,
    default: ''
  },


  /**
   * 是否显示趋势
   */
  showTrend: {
    type: Boolean,
    default: false
  },


  /**
   * 趋势类型
   *
   * up
   * down
   * neutral
   */
  trend: {
    type: String,
    default: 'neutral'
  },


  /**
   * 趋势文字
   *
   * 例如：
   * +12.5%
   * -3.2%
   */
  trendText: {
    type: String,
    default: ''
  }

})


/**
 * =========================================================
 * 数值显示
 * =========================================================
 */

const displayValue = computed(() => {

  if (
      props.value === null ||
      props.value === undefined
  ) {
    return '-'
  }

  return props.value
})


/**
 * =========================================================
 * 趋势样式
 * =========================================================
 */

const trendClass = computed(() => {

  switch (props.trend) {

    case 'up':
      return 'trend-up'

    case 'down':
      return 'trend-down'

    default:
      return 'trend-neutral'
  }
})


/**
 * =========================================================
 * 趋势图标
 * =========================================================
 */

const trendIcon = computed(() => {

  switch (props.trend) {

    case 'up':
      return ArrowUp

    case 'down':
      return ArrowDown

    default:
      return Minus
  }
})

</script>


<style scoped>

.stat-card {
  width: 100%;
  border-radius: 12px;
  overflow: hidden;

  transition:
      transform 0.2s ease,
      box-shadow 0.2s ease;
}


.stat-card:hover {
  transform: translateY(-2px);
}


/* =========================================================
   内容
   ========================================================= */

.stat-card-content {
  display: flex;
  align-items: center;

  min-height: 110px;

  position: relative;
}


/* =========================================================
   图标
   ========================================================= */

.stat-icon {
  width: 52px;
  height: 52px;

  margin-right: 16px;

  display: flex;
  align-items: center;
  justify-content: center;

  border-radius: 12px;

  background: var(--smart-bg);

  flex-shrink: 0;
}


/* =========================================================
   主数据
   ========================================================= */

.stat-main {
  min-width: 0;
  flex: 1;
}


.stat-title {
  color: var(--smart-muted);

  font-size: 14px;

  line-height: 22px;

  white-space: nowrap;

  overflow: hidden;

  text-overflow: ellipsis;
}


.stat-value {
  margin-top: 4px;

  font-size: 30px;

  font-weight: 700;

  line-height: 40px;

  color: var(--smart-text);
}


.stat-description {
  margin-top: 2px;

  color: var(--smart-muted);

  font-size: 12px;

  line-height: 18px;
}


/* =========================================================
   趋势
   ========================================================= */

.stat-trend {
  align-self: flex-start;

  display: flex;

  align-items: center;

  gap: 3px;

  margin-left: 10px;

  padding: 4px 7px;

  border-radius: 6px;

  font-size: 12px;

  white-space: nowrap;
}


.trend-up {
  color: var(--smart-success);

  background: rgba(
      34,
      197,
      94,
      0.08
  );
}


.trend-down {
  color: var(--smart-danger);

  background: rgba(
      239,
      68,
      68,
      0.08
  );
}


.trend-neutral {
  color: var(--smart-muted);

  background: var(--smart-bg);
}


/* =========================================================
   类型
   ========================================================= */

.stat-card-primary .stat-icon {
  color: var(--smart-primary);
}


.stat-card-success .stat-icon {
  color: var(--smart-success);
}


.stat-card-warning .stat-icon {
  color: var(--smart-warning);
}


.stat-card-danger .stat-icon {
  color: var(--smart-danger);
}


.stat-card-info .stat-icon {
  color: #64748b;
}


/* =========================================================
   响应式
   ========================================================= */

@media (max-width: 700px) {

  .stat-card-content {
    min-height: 95px;
  }


  .stat-icon {
    width: 44px;
    height: 44px;

    margin-right: 12px;
  }


  .stat-value {
    font-size: 26px;
  }


  .stat-trend {
    display: none;
  }

}

</style>