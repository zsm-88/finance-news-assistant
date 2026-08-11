"""Debug why events page is 500."""
import starlette.templating
import inspect
src = inspect.getsource(starlette.templating.Jinja2Templates.TemplateResponse)
print(src)
print("---")
# Also check the Jinja2Templates init
src2 = inspect.getsource(starlette.templating.Jinja2Templates.__init__)
print(src2)