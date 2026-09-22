"""Все пороги audit_project в одном месте: меняйте здесь."""

# прогон
DEFAULT_VIEWPORTS = (375, 768, 1280)
VIEWPORT_HEIGHTS = {375: 812, 768: 1024, 1280: 800}   # для прочих ширин высота 800
DEFAULT_HEIGHT = 800
DEFAULT_MAX_PAGES = 10

# network
NETWORK_IDLE_WAIT_MS = 5000   # сколько ждать тишины в сети перед разбором запросов
SLOW_REQUEST_NOTICE_MS = 1000
SLOW_REQUEST_WARNING_MS = 3000

# images
IMAGE_NOTICE_BYTES = 200 * 1024
IMAGE_WARNING_BYTES = 1024 * 1024
IMAGE_OVERSIZE_RATIO = 2.0

# accessibility
AXE_MAX_NODES_PER_RULE = 20       # не больше стольких элементов на одно правило axe на странице
FOCUS_TAB_STOPS = 20              # сколько раз нажимать Tab
FOCUS_MIN_CHANGED_PIXELS = 4      # столько пикселей должно измениться, чтобы фокус считался видимым

# layout
TAP_TARGET_MIN_PX = 24
TAP_TARGET_VIEWPORT = 375
MAX_SMALL_TARGETS = 20          # не больше стольких мелких зон нажатия на страницу

# performance
LOAD_WARNING_MS = 3000
LCP_NOTICE_MS = 2500
LCP_WARNING_MS = 4000
CLS_NOTICE = 0.1
CLS_WARNING = 0.25
PAGE_WEIGHT_WARNING_BYTES = 3 * 1024 * 1024
REQUEST_COUNT_NOTICE = 100
JS_FILE_WARNING_BYTES = 500 * 1024
CSS_FILE_NOTICE_BYTES = 150 * 1024

# interactions
MAX_CLICKS_PER_PAGE = 20
CLICK_OBSERVE_MS = 2000
