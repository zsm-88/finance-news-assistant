"""Debug: check how TemplateResponse is called in the running container."""
import app.admin.router as r
import inspect
src = inspect.getsource(r.dashboard)
print(src)