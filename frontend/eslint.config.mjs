import js from "@eslint/js";
import pluginVue from "eslint-plugin-vue";
import globals from "globals";

export default [
  {
    // 构建产物、依赖与 TS 源码不在此轮范围内（TS 由 vite/tsc 负责）。
    ignores: [
      "node_modules/**",
      "dist/**",
      "dist-admin/**",
      "**/dist-*/**",
      "**/.vite-*/**",
      "**/test-artifacts/**",
      // TS 由 vite/tsc 负责，不在本轮 lint 范围
      "**/*.ts",
    ],
  },

  js.configs.recommended,
  ...pluginVue.configs["flat/essential"],

  {
    files: ["**/*.{js,mjs,vue}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
        // Vue 编译宏
        defineProps: "readonly",
        defineEmits: "readonly",
        defineExpose: "readonly",
        withDefaults: "readonly",
      },
    },
    rules: {
      // 存量代码较多，未使用变量先作为提示而非阻断。
      "no-unused-vars": ["warn", { args: "none", varsIgnorePattern: "^_" }],
      "no-empty": ["error", { allowEmptyCatch: true }],
      // 中文全角空格用于缩进展示，属有意为之
      "no-irregular-whitespace": ["error", { skipStrings: true }],
      // 输入校验/脱敏处有意匹配控制字符
      "no-control-regex": "off",
      "vue/multi-word-component-names": "off",
    },
  },
];
