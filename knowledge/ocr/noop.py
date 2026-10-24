class NoopOCR:

    def extract_text(
        self,
        image_path: str,
    ) -> str:

        raise NotImplementedError(
            "OCR 当前未启用，请安装并配置真实 OCR 引擎；系统不会生成模拟识别结果"
        )
