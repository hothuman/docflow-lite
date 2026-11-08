"""Navigation for local workspace tasks inside the main window."""
from dataclasses import dataclass
from collections.abc import Callable

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from ..widgets import text
from .widgets import button


@dataclass
class Route:
    widget: QWidget
    title: str
    back_label: str
    before_close: Callable | None
    on_close: Callable | None
    previous_focus: QWidget | None


class WorkspacePages(QWidget):
    changed = Signal()

    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.routes = []
        self._clearing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.back_button = button(bar, 'Назад', self.back)
        self.crumbs = text('', 'workspaceBreadcrumb')
        self.crumbs.setWordWrap(False)
        self.crumbs.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        bar.addWidget(self.crumbs,1)
        layout.addLayout(bar)
        self.caption=''
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.escape = QShortcut(QKeySequence('Esc'), self)
        self.escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape.activated.connect(self.back)
        self.hide()

    @property
    def current(self):
        return self.routes[-1].widget if self.routes else None

    @property
    def titles(self):
        return [route.widget.windowTitle() or route.title for route in self.routes]

    def push(self, widget, title, *, back_label='Назад', before_close=None, on_close=None):
        focus = self.workspace.window().focusWidget()
        if isinstance(widget, QDialog):
            widget.setParent(self.stack, Qt.WindowType.Widget)
            widget.setModal(False)
            widget.setMinimumSize(0, 0)
            widget.finished.connect(lambda _: self.finished(widget))
        self.routes.append(Route(widget, title, back_label, before_close, on_close, focus))
        self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)
        widget.show()
        self.show()
        self.update_heading()
        self.changed.emit()
        self.back_button.setFocus(Qt.FocusReason.OtherFocusReason)
        return widget

    def update_heading(self):
        if not self.routes:
            return
        route = self.routes[-1]
        label = route.back_label
        self.back_button.setText(label)
        self.back_button.setAccessibleName(label)
        source = self.workspace.tabs.tabText(self.workspace.tabs.currentIndex())
        detail = getattr(route.widget, 'route_detail', '')
        self.caption = ' / '.join(filter(None, ('Мастерская', source, *self.titles, detail)))
        self.crumbs.setAccessibleName(self.caption)
        self.crumbs.setToolTip(self.caption)
        self.fit_crumbs()

    def fit_crumbs(self):
        self.crumbs.setText(self.crumbs.fontMetrics().elidedText(
            self.caption,Qt.TextElideMode.ElideMiddle,self.crumbs.width()))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.fit_crumbs()

    def finished(self, widget):
        if widget is self.current:
            self.pop()

    def back(self, *_):
        if self.routes and not self.workspace.worker:
            self._leave(self.routes[-1], self.pop)

    def _leave(self, route, proceed):
        if route.before_close:
            route.before_close(proceed)
        elif isinstance(route.widget, QDialog):
            route.widget.reject()
        else:
            proceed()

    def pop(self, notify=True):
        if not self.routes:
            return
        route = self.routes.pop()
        self.stack.removeWidget(route.widget)
        route.widget.hide()
        route.widget.deleteLater()
        self.setVisible(bool(self.routes))
        self.update_heading()
        self.changed.emit()
        if route.previous_focus and route.previous_focus.isVisible() and route.previous_focus.isEnabled():
            route.previous_focus.setFocus(Qt.FocusReason.OtherFocusReason)
        if notify and not self._clearing and route.on_close:
            route.on_close()

    def clear(self, completed):
        self.return_to(None, completed)

    def return_to(self, target, completed=lambda:None):
        if self.workspace.worker:
            return
        if self.current is target:
            completed()
            return
        if not self.routes:
            return
        route = self.routes[-1]

        def next_page():
            if self.current is route.widget:
                self.pop(notify=False)
            self.return_to(target, completed)

        if route.before_close:
            route.before_close(next_page)
        elif isinstance(route.widget, QDialog):
            # A dialog may veto rejection while it has an unsaved draft.
            # A successful rejection emits finished synchronously.
            self._clearing=True
            try:route.widget.reject()
            finally:self._clearing=False
            if self.current is not route.widget:
                self.return_to(target, completed)
        else:
            next_page()
