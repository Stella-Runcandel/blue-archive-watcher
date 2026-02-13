from app.app_state import app_state


class NavigationController:
    def __init__(self, stack_layout):
        self.stack = stack_layout

    def push(self, widget, name):
        app_state.nav_stack.append(name)
        self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)

        if hasattr(self.stack.parentWidget(), "nav_bar"):
            self.stack.parentWidget().nav_bar.hide()

    def pop(self):
        if len(app_state.nav_stack) <= 1:
            return  # don't pop dashboard

        # remove current widget
        current_widget = self.stack.currentWidget()
        if hasattr(current_widget, "on_panel_close"):
            current_widget.on_panel_close()
        self.stack.removeWidget(current_widget)
        current_widget.deleteLater()

        # update nav stack
        app_state.nav_stack.pop()

        # show previous widget
        self.stack.setCurrentIndex(self.stack.count() - 1)
        
        if len(app_state.nav_stack) == 1:
            parent = self.stack.parentWidget()
            if hasattr(parent, "nav_bar"):
                parent.nav_bar.show()
                
        # notify dashboard when returning
        current = self.stack.currentWidget()
        if hasattr(current, "refresh"):
            current.refresh()

    def current(self):
        return app_state.nav_stack[-1]
