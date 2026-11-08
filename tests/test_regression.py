import os,re,io,subprocess,tempfile,unittest,zipfile
from pathlib import Path
TEMP=tempfile.TemporaryDirectory(); ROOT=Path(TEMP.name); (ROOT/'share').mkdir()
os.environ.update(DATA_DIR=str(ROOT/'data'),SHARE_PATH=str(ROOT/'share'),ADMIN_PASSWORD='test-admin',SECRET_KEY='isolated-test-secret',TELEGRAM_BOT_TOKEN='',TELEGRAM_ALLOWED_IDS='',PUID='1000',PGID='1000',MCP_TOKEN='isolated-mcp-token')
from fastapi.testclient import TestClient
from app import main as m
class Regression(unittest.TestCase):
    def setUp(self):
        for f,v in ((m.SF,{}),(m.FF,[]),(m.PF,[]),(m.TJ,[]),(m.MCP._tf(),[])): m.save(f,v)
        m.fails.clear(); self.c=TestClient(m.app)
    def login(self): self.assertEqual(self.c.post('/api/login',json={'password':'test-admin'}).status_code,200)
    def test_auth(self):
        for path in ('/api/list','/api/settings','/api/mcp','/api/backup'): self.assertEqual(self.c.get(path).status_code,401)
        self.assertEqual(self.c.post('/api/login',json={'password':'bad'}).status_code,401)
        self.login(); self.assertTrue(self.c.get('/api/me').json()['auth'])
        self.assertEqual(self.c.post('/api/password',json={'password':'new-password'}).status_code,200)
        self.assertEqual(self.c.get('/api/list').status_code,401)
        self.assertEqual(self.c.post('/api/login',json={'password':'test-admin'}).status_code,401)
        self.assertEqual(self.c.post('/api/login',json={'password':'new-password'}).status_code,200)
        self.c.post('/api/logout'); self.assertFalse(self.c.get('/api/me').json()['auth'])
    def test_routes(self):
        seen=set()
        for route in m.app.routes:
            for method in getattr(route,'methods',[]):
                key=(method,re.sub(r'\{[^}]+\}','{}',route.path)); self.assertNotIn(key,seen); seen.add(key)
        self.assertNotIn(('GET','/api/debug/checkpw'),seen)
    def test_files_backup(self):
        self.login(); self.assertEqual(self.c.get('/api/list',params={'path':'../'}).status_code,400)
        m.save(m.SF,{'trash_enabled':False}); (m.ROOT/'delete.txt').write_text('x')
        self.assertEqual(self.c.post('/api/delete',json={'path':'delete.txt'}).status_code,200)
        with zipfile.ZipFile(io.BytesIO(self.c.get('/api/backup').content)) as z: self.assertIn('settings.json',z.namelist())
    def test_slicer(self):
        self.login(); image=b'\x89PNG\r\n\x1a\nfixture'
        with zipfile.ZipFile(m.ROOT/'model.3mf','w') as z: z.writestr('Metadata/thumbnail.png',image)
        self.assertEqual(self.c.get('/api/slicer/image',params={'path':'model.3mf'}).content,image)
    def test_mcp(self):
        self.login(); token=self.c.post('/api/mcp/tokens',json={'ro':True}).json()['token']
        result=self.c.post('/mcp',headers={'Authorization':'Bearer '+token},json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).json()
        names={x['name'] for x in result['result']['tools']}; self.assertIn('get_cost_summary',names); self.assertNotIn('write_file',names)
        self.assertNotIn(token,self.c.get('/api/mcp').text)
    def test_frontend(self):
        subprocess.run(['node','--check','app/static/app.js'],check=True)
        html=Path('app/static/index.html').read_text()
        self.assertIn('/app.js?v=login-v2',html)
        ids=re.findall(r'\bid="([^"]+)"',html)
        # Debug: Zähle IDs
        print(f"Total IDs: {len(ids)}")
        print(f"Unique IDs: {len(set(ids))}")
        from collections import Counter
        counts = Counter(ids)
        duplicates = [id for id, count in counts.items() if count > 1]
        print("Duplicate IDs:", duplicates)
        if duplicates:
            print("Locations of duplicates:")
            for dup in duplicates:
                pattern = rf'id="{re.escape(dup)}"'
                matches = list(re.finditer(pattern, html))
                for i, match in enumerate(matches):
                    start = max(0, match.start() - 50)
                    end = min(len(html), match.end() + 50)
                    print(f"  {dup} occurrence {i+1}: ...{html[start:end]}...")
            self.assertEqual(len(ids),len(set(ids)))
if __name__=='__main__': unittest.main()
