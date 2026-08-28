import enum


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    PARSING_DOCUMENT = "PARSING_DOCUMENT"
    GENERATING_REPORT = "GENERATING_REPORT"
    FINDING_RELATED_WORK = "FINDING_RELATED_WORK"
    WRITING_REPORT = "WRITING_REPORT"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

    @classmethod
    def description(cls, status):
        desc_map = {
            cls.PENDING: "排队中",
            cls.PARSING_DOCUMENT: "解析论文",
            cls.GENERATING_REPORT: "生成阅读报告",
            cls.FINDING_RELATED_WORK: "检索近邻论文",
            cls.WRITING_REPORT: "生成报告",
            cls.SUCCESS: "完成",
            cls.FAILED: "失败",
        }
        return desc_map.get(status, "未知状态")
