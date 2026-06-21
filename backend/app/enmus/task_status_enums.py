import enum


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    PARSING = "PARSING"
    DOWNLOADING = "DOWNLOADING"
    TRANSCRIBING = "TRANSCRIBING"
    SUMMARIZING = "SUMMARIZING"
    FORMATTING = "FORMATTING"
    SAVING = "SAVING"
    EXTRACTING_CLAIMS = "EXTRACTING_CLAIMS"
    SEARCHING_WEB = "SEARCHING_WEB"
    FETCHING_SOURCES = "FETCHING_SOURCES"
    EVALUATING_EVIDENCE = "EVALUATING_EVIDENCE"
    WRITING_REPORT = "WRITING_REPORT"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

    @classmethod
    def description(cls, status):
        desc_map = {
            cls.PENDING: "排队中",
            cls.PARSING: "解析链接",
            cls.DOWNLOADING: "下载中",
            cls.TRANSCRIBING: "转录中",
            cls.SUMMARIZING: "总结中",
            cls.FORMATTING: "格式化中",
            cls.SAVING: "保存中",
            cls.EXTRACTING_CLAIMS: "提取主张",
            cls.SEARCHING_WEB: "联网检索",
            cls.FETCHING_SOURCES: "抓取证据",
            cls.EVALUATING_EVIDENCE: "交叉判定",
            cls.WRITING_REPORT: "生成报告",
            cls.SUCCESS: "完成",
            cls.FAILED: "失败",
        }
        return desc_map.get(status, "未知状态")
