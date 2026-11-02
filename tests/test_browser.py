import os,socket,subprocess,sys,tempfile,time,unittest,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

class BrowserLogin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(); root=Path(cls.temp.name); (root/'share').mkdir()
        with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        cls.url=f'http://127.0.0.1:{port}'
        env={**os.environ,'DATA_DIR':str(root/'data'),'SHARE_PATH':str(root/'share'),'ADMIN_PASSWORD':'browser-test-only','SECRET_KEY':'browser-test-secret','TELEGRAM_BOT_TOKEN':'','TELEGRAM_ALLOWED_IDS':'','LLM_BASE_URL':'','LLM_MODEL':'','PUID':str(os.getuid()),'PGID':str(os.getgid())}
        cls.server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.addClassCleanup(cls.stop_server)
        for _ in range(100):
            if cls.server.poll() is not None: raise RuntimeError('Browser test server exited')
            try:
                with urllib.request.urlopen(cls.url+'/health',timeout=.3) as response:
                    if response.status==200: break
            except OSError: time.sleep(.1)
        else: raise RuntimeError('Browser test server did not start')
        cls.playwright=sync_playwright().start(); cls.addClassCleanup(cls.playwright.stop)
        cls.browser=cls.playwright.chromium.launch(); cls.addClassCleanup(cls.browser.close)
    @classmethod
    def stop_server(cls):
        cls.server.terminate()
        try: cls.server.wait(timeout=5)
        except subprocess.TimeoutExpired: cls.server.kill(); cls.server.wait()
        cls.temp.cleanup()
    def setUp(self):
        self.context=self.browser.new_context(); self.addCleanup(self.context.close)
        self.page=self.context.new_page(); self.errors=[]; self.page.on('pageerror',lambda error:self.errors.append(str(error)))
        self.page.goto(self.url)
        self.page.wait_for_function("!document.getElementById('loginButton').disabled")
    def login(self,enter=False):
        self.page.fill('#pw','browser-test-only')
        if enter: self.page.press('#pw','Enter')
        else: self.page.click('#loginButton')
        self.page.wait_for_function("document.getElementById('login').hidden && !document.getElementById('app').hidden")
        self.assertEqual(self.errors,[])
    def test_click_reload_logout(self):
        self.login()
        self.assertTrue(self.context.request.get(self.url+'/api/me').json()['auth'])
        self.page.reload(); self.page.wait_for_function("!document.getElementById('app').hidden")
        self.page.click('#lo'); self.page.wait_for_function("!document.getElementById('login').hidden")
        self.assertFalse(self.context.request.get(self.url+'/api/me').json()['auth'])
    def test_enter(self): self.login(enter=True)
    def test_wrong_password_visible(self):
        self.page.fill('#pw','wrong-test-only'); self.page.click('#loginButton')
        self.page.wait_for_function("document.getElementById('loginStatus').textContent.includes('Falsches Passwort')")
        self.assertTrue(self.page.is_enabled('#loginButton')); self.assertTrue(self.page.is_visible('#login'))
    def test_server_error_visible(self):
        self.page.route('**/api/login',lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"Testserver nicht bereit"}'))
        self.page.fill('#pw','browser-test-only'); self.page.click('#loginButton')
        self.page.wait_for_function("document.getElementById('loginStatus').textContent.includes('Testserver nicht bereit')")
        self.assertTrue(self.page.is_enabled('#loginButton'))
    def test_missing_cookie_visible(self):
        self.page.route('**/api/me',lambda route:route.fulfill(content_type='application/json',body='{"auth":false}'))
        self.page.fill('#pw','browser-test-only'); self.page.click('#loginButton')
        self.page.wait_for_function("document.getElementById('loginStatus').textContent.includes('Session-Cookie fehlt')")
        self.assertTrue(self.page.is_visible('#login'))

if __name__=='__main__': unittest.main()
