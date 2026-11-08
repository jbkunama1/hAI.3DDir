import io,json,shutil,unittest,uuid,zipfile
from pathlib import Path
import test_browser as infrastructure
from playwright.sync_api import expect

class RestoredControls(infrastructure.BrowserLogin):
    def setUp(self):
        super().setUp()
            # Auf aktuellen Build warten, nicht auf restaurierten Controls
            self.page.wait_for_function("!document.documentElement.dataset.controls")
        self.case='case-'+uuid.uuid4().hex[:10]
        self.folder=Path(self.temp.name)/'share'/self.case
        (self.folder/'destination').mkdir(parents=True)
        (self.folder/'alpha.txt').write_text('alpha')
        (self.folder/'beta.txt').write_text('beta')
        self.addCleanup(lambda:shutil.rmtree(self.folder,ignore_errors=True))
    def enter_case(self):
        self.login()
        self.page.click('#gr .card[data-path="'+self.case+'"] .open')
        expect(self.page.locator('#gr .card[data-path="'+self.case+'/alpha.txt"] .itemSelect')).to_have_count(1)
    def choose(self,*names):
        if self.page.locator('#selectionMode').get_attribute('aria-pressed')!='true': self.page.click('#selectionMode')
        for name in names: self.page.locator('#gr .card[data-path="'+self.case+'/'+name+'"] .itemSelect').check()
    def test_multi_select_zip(self):
        self.enter_case(); self.choose('alpha.txt','beta.txt')
        expect(self.page.locator('#selectionCount')).to_have_text('2 ausgewählt')
        with self.page.expect_download() as pending: self.page.click('#batchZip')
        path=Path(self.temp.name)/('download-'+uuid.uuid4().hex+'.zip'); pending.value.save_as(path)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(set(archive.namelist()),{'alpha.txt','beta.txt'})
            self.assertEqual(archive.read('alpha.txt'),b'alpha')
        self.assertEqual(self.errors,[])
    def test_move_selected(self):
        self.enter_case(); self.choose('alpha.txt','beta.txt'); self.page.click('#batchMove')
        self.page.click('#moveFolders [data-path="'+self.case+'/destination"]')
        expect(self.page.locator('#movePath')).to_have_text('/'+self.case+'/destination')
        self.page.once('dialog',lambda dialog:dialog.accept()); self.page.click('#moveHere')
        expect(self.page.locator('#moveDialog')).not_to_be_visible()
        self.assertTrue((self.folder/'destination'/'alpha.txt').exists()); self.assertTrue((self.folder/'destination'/'beta.txt').exists())
        self.assertFalse((self.folder/'alpha.txt').exists()); self.assertEqual(self.errors,[])
    def test_delete_restore_and_purge(self):
        self.enter_case(); self.choose('alpha.txt'); self.page.once('dialog',lambda dialog:dialog.accept()); self.page.click('#batchDelete')
        expect(self.page.locator('#toast')).to_contain_text('1 gelöscht; 0 fehlgeschlagen')
        self.page.click('nav [data-t="trash"]')
        row=self.page.locator('#trashRows [data-origin="'+self.case+'/alpha.txt"]')
        row.locator('[data-action="restore"]').click(); expect(row).to_have_count(0)
        self.assertTrue((self.folder/'alpha.txt').exists())
        self.page.click('nav [data-t="files"]'); self.choose('beta.txt'); self.page.once('dialog',lambda dialog:dialog.accept()); self.page.click('#batchDelete')
        expect(self.page.locator('#toast')).to_contain_text('1 gelöscht; 0 fehlgeschlagen'); self.page.click('nav [data-t="trash"]')
        row=self.page.locator('#trashRows [data-origin="'+self.case+'/beta.txt"]'); self.page.once('dialog',lambda dialog:dialog.accept()); row.locator('[data-action="purge"]').click(); expect(row).to_have_count(0)
        self.assertEqual(self.errors,[])
    def test_partial_delete_failure_visible(self):
        self.enter_case(); self.choose('alpha.txt','beta.txt')
        def intercept(route):
            if route.request.post_data_json['path'].endswith('/beta.txt'): route.fulfill(status=503,content_type='application/json',body='{"detail":"Testfehler"}')
            else: route.continue_()
        self.page.route('**/api/delete',intercept); self.page.once('dialog',lambda dialog:dialog.accept()); self.page.click('#batchDelete')
        expect(self.page.locator('#toast')).to_contain_text('1 gelöscht; 1 fehlgeschlagen')
        self.assertFalse((self.folder/'alpha.txt').exists()); self.assertTrue((self.folder/'beta.txt').exists())
        expect(self.page.locator('#selectionCount')).to_have_text('1 ausgewählt')
    def test_new_folder_and_drag_upload(self):
        self.enter_case(); self.page.once('dialog',lambda dialog:dialog.accept('created')); self.page.click('#newFolder')
        expect(self.page.locator('#gr .card[data-path="'+self.case+'/created"]')).to_have_count(1)
        transfer=self.page.evaluate_handle("()=>{const d=new DataTransfer();d.items.add(new File(['drag-test'],'drag.txt',{type:'text/plain'}));return d;}")
        self.page.dispatch_event('#gr','drop',{'dataTransfer':transfer})
        expect(self.page.locator('#uploadStatus')).to_contain_text('1 Datei(en) hochgeladen')
        self.assertEqual((self.folder/'drag.txt').read_text(),'drag-test'); self.assertEqual(self.errors,[])
    def test_import_append_and_replace(self):
        self.login(); self.page.click('nav [data-t="fil"]')
        content=json.dumps([{'brand':self.case,'material':'PLA','weight_total':1000,'weight_remaining':800}]).encode()
        self.page.locator('#filamentImport').set_input_files({'name':'spools.json','mimeType':'application/json','buffer':content})
        expect(self.page.locator('#toast')).to_contain_text('1 Rollen importiert')
        expect(self.page.locator('#ft')).to_contain_text(self.case)
        self.page.locator('#replaceFilaments').check(); self.page.once('dialog',lambda dialog:dialog.accept())
        self.page.locator('#filamentImport').set_input_files({'name':'empty.json','mimeType':'application/json','buffer':b'[]'})
        expect(self.page.locator('#toast')).to_contain_text('0 Rollen importiert'); expect(self.page.locator('#ft tr')).to_have_count(0)
        self.assertEqual(self.errors,[])

if __name__=='__main__': unittest.main()
