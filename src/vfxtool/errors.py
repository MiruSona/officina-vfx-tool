"""종료 코드 2(인자 · 파일 · 환경 · 예외)로 끝낼 오류. 규칙 위반은 예외가 아니라 issues 로 돌린다."""


class VfxError(Exception):
    """사람이 읽을 한국어 message 를 담는다."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message
