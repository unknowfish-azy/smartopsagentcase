<template>
  <section
      class="app-card"
      :class="[
      `app-card-${type}`,
      {
        'is-hoverable': hoverable,
        'is-borderless': borderless,
        'is-compact': compact
      }
    ]"
  >

    <!-- ==============================
         卡片头部
         ============================== -->
    <header
        v-if="
        title ||
        subtitle ||
        $slots.header ||
        $slots.extra
      "
        class="app-card-header"
    >

      <!-- 左侧标题 -->
      <div class="app-card-header-main">

        <!-- 自定义Header插槽 -->
        <slot name="header">

          <div class="app-card-title-row">

            <span
                v-if="icon"
                class="app-card-icon"
            >
              <el-icon :size="iconSize">
                <component :is="icon" />
              </el-icon>
            </span>

            <div class="app-card-title-wrapper">

              <h3
                  v-if="title"
                  class="app-card-title"
              >
                {{ title }}
              </h3>

              <p
                  v-if="subtitle"
                  class="app-card-subtitle"
              >
                {{ subtitle }}
              </p>

            </div>

          </div>

        </slot>

      </div>


      <!-- 右侧操作 -->
      <div
          v-if="$slots.extra || showExtra"
          class="app-card-extra"
      >

        <slot name="extra">

          <el-button
              v-if="extraText"
              link
              type="primary"
              @click="$emit('extra')"
          >
            {{ extraText }}
          </el-button>

        </slot>

      </div>

    </header>


    <!-- ==============================
         Loading遮罩
         ============================== -->
    <div
        v-loading="loading"
        class="app-card-body"
        :class="{
        'has-padding': bodyPadding
      }"
        element-loading-text="加载中..."
    >

      <!-- 默认内容 -->
      <slot />

    </div>


    <!-- ==============================
         Footer
         ============================== -->
    <footer
        v-if="$slots.footer"
        class="app-card-footer"
    >

      <slot name="footer" />

    </footer>

  </section>
</template>


<script setup>

defineProps({

  /**
   * 卡片标题
   */
  title: {
    type: String,
    default: ''
  },


  /**
   * 卡片副标题
   */
  subtitle: {
    type: String,
    default: ''
  },


  /**
   * 卡片图标
   *
   * 使用Element Plus Icon
   */
  icon: {
    type: [Object, Function],
    default: null
  },


  /**
   * 图标大小
   */
  iconSize: {
    type: Number,
    default: 20
  },


  /**
   * 卡片类型
   *
   * default
   * primary
   * success
   * warning
   * danger
   * info
   */
  type: {
    type: String,
    default: 'default'
  },


  /**
   * 是否加载中
   */
  loading: {
    type: Boolean,
    default: false
  },


  /**
   * 是否显示内容内边距
   */
  bodyPadding: {
    type: Boolean,
    default: true
  },


  /**
   * 是否支持hover效果
   */
  hoverable: {
    type: Boolean,
    default: false
  },


  /**
   * 是否取消边框
   */
  borderless: {
    type: Boolean,
    default: false
  },


  /**
   * 是否使用紧凑模式
   */
  compact: {
    type: Boolean,
    default: false
  },


  /**
   * 是否显示右侧默认操作
   */
  showExtra: {
    type: Boolean,
    default: false
  },


  /**
   * 默认操作文字
   */
  extraText: {
    type: String,
    default: ''
  }

})


defineEmits([
  'extra'
])

</script>


<style scoped>

.app-card {

  width: 100%;

  background:
      var(--smart-card, #ffffff);

  border:
      1px solid
      var(--smart-border, #e5e7eb);

  border-radius: 12px;

  overflow: hidden;

  transition:
      transform 0.2s ease,
      box-shadow 0.2s ease,
      border-color 0.2s ease;

}


/* =========================================================
   Hover
   ========================================================= */

.app-card.is-hoverable:hover {

  transform:
      translateY(-2px);

  box-shadow:
      0 8px 24px
      rgba(0, 0, 0, 0.06);

}


/* =========================================================
   无边框
   ========================================================= */

.app-card.is-borderless {

  border: none;

}


/* =========================================================
   紧凑模式
   ========================================================= */

.app-card.is-compact
.app-card-body {

  padding-top: 12px;

  padding-bottom: 12px;

}


/* =========================================================
   Header
   ========================================================= */

.app-card-header {

  min-height: 58px;

  display: flex;

  align-items: center;

  justify-content: space-between;

  gap: 16px;

  padding:
      14px
      18px;

  border-bottom:
      1px solid
      var(--smart-border, #e5e7eb);

}


.app-card-header-main {

  min-width: 0;

  flex: 1;

}


.app-card-title-row {

  display: flex;

  align-items: center;

  gap: 10px;

}


.app-card-title-wrapper {

  min-width: 0;

}


.app-card-icon {

  width: 34px;

  height: 34px;

  display: flex;

  align-items: center;

  justify-content: center;

  flex-shrink: 0;

  border-radius: 8px;

  background:
      var(--smart-bg, #f5f7fa);

  color:
      var(--smart-primary, #1677ff);

}


.app-card-title {

  margin: 0;

  font-size: 16px;

  font-weight: 600;

  line-height: 24px;

  color:
      var(--smart-text, #1f2937);

  white-space: nowrap;

  overflow: hidden;

  text-overflow: ellipsis;

}


.app-card-subtitle {

  margin: 3px 0 0;

  color:
      var(--smart-muted, #6b7280);

  font-size: 12px;

  line-height: 18px;

}


/* =========================================================
   Extra
   ========================================================= */

.app-card-extra {

  display: flex;

  align-items: center;

  flex-shrink: 0;

}


/* =========================================================
   Body
   ========================================================= */

.app-card-body {

  position: relative;

  min-height: 20px;

}


.app-card-body.has-padding {

  padding: 18px;

}


/* =========================================================
   Footer
   ========================================================= */

.app-card-footer {

  padding:
      12px
      18px;

  border-top:
      1px solid
      var(--smart-border, #e5e7eb);

  color:
      var(--smart-muted, #6b7280);

  font-size: 13px;

}


/* =========================================================
   类型
   ========================================================= */

.app-card-primary {

  border-top:
      2px solid
      var(--smart-primary, #1677ff);

}


.app-card-success {

  border-top:
      2px solid
      var(--smart-success, #22c55e);

}


.app-card-warning {

  border-top:
      2px solid
      var(--smart-warning, #f59e0b);

}


.app-card-danger {

  border-top:
      2px solid
      var(--smart-danger, #ef4444);

}


/* =========================================================
   Responsive
   ========================================================= */

@media (max-width: 650px) {

  .app-card-header {

    padding:
        12px
        14px;

  }


  .app-card-body.has-padding {

    padding: 14px;

  }


  .app-card-footer {

    padding:
        10px
        14px;

  }

}

</style>