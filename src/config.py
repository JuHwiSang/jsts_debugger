from typing import Literal, get_args

AllowedDebuggerCommand = Literal[
    "Debugger.enable",
    "Runtime.enable",
    "Network.enable",
    "HeapProfiler.enable",
    "Profiler.enable",
    # ── 실행 제어 ──────────────────────────────────────────
    "Debugger.resume",           # 실행 계속
    "Debugger.pause",            # 실행 중단
    "Debugger.stepOver",         # 다음 문장까지 진행
    "Debugger.stepInto",         # 함수 내부로 진입
    "Debugger.stepOut",          # 호출 스택 밖으로
    # ── 브레이크포인트 ───────────────────────────────────
    "Debugger.setBreakpointByUrl",        # URL/라인 기준 BP
    "Debugger.setBreakpointOnFunctionCall",# 함수 호출 시 BP
    "Debugger.removeBreakpoint",          # BP 해제
    "Debugger.setSkipAllPauses",          # 모든 BP 무시
    "Debugger.setBlackboxPatterns",       # 라이브러리 스텝-인 차단
    "Debugger.setPauseOnExceptions",      # 예외 발생 시 중단
    # ── 소스 & 스택 ─────────────────────────────────────
    "Debugger.getScriptSource",  # 스크립트 원본 조회
    "Debugger.getStackTrace",    # 스택트레이스 가져오기
    # ── 런타임 평가 ─────────────────────────────────────
    "Runtime.evaluate",          # 표현식 평가
    "Debugger.evaluateOnCallFrame",
    "Runtime.callFunctionOn",    # 객체 메서드 호출
    "Runtime.getProperties",     # 객체 속성 열람
    "Runtime.runIfWaitingForDebugger",
    # ── 메모리 / 힙 ────────────────────────────────────
    "HeapProfiler.takeHeapSnapshot",  # 힙 스냅샷
    "HeapProfiler.startSampling",     # 힙 샘플링 시작
    "HeapProfiler.stopSampling",      # 힙 샘플링 중단
    # ── CPU / 커버리지 ─────────────────────────────────
    "Profiler.enable",           # 프로파일러 준비
    "Profiler.start",            # CPU 프로파일 시작
    "Profiler.stop",             # CPU 프로파일 종료
    "Profiler.startPreciseCoverage",   # 상세 커버리지 시작
    "Profiler.takePreciseCoverage",    # 커버리지 캡처
    "Profiler.stopPreciseCoverage",    # 커버리지 종료
    # ── 네트워크 ───────────────────────────────────────
    "Network.enable",            # 네트워크 이벤트 수집
]

allowed_debugger_commands: list[AllowedDebuggerCommand] = list(get_args(AllowedDebuggerCommand))
allowed_debugger_commands_set: set[AllowedDebuggerCommand] = set(get_args(AllowedDebuggerCommand))

entrypoint_ts_path = "/app/entrypoint.ts"