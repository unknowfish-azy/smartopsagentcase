<template>
  <div class="not-found">

    <div class="code">404</div>

    <h2>页面不存在</h2>

    <p>
      你访问的页面不存在
    </p>

    <el-button
        type="primary"
        @click="goHome"
    >
      返回首页
    </el-button>

  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/')
}
</script>

<style scoped>
.not-found {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.code {
  font-size: 96px;
  font-weight: 800;
  color: var(--smart-primary);
}

h2 {
  margin: 10px 0;
}

p {
  color: var(--smart-muted);
}
</style>
