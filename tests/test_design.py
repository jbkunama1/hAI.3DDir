import unittest
import test_browser as infrastructure
from playwright.sync_api import expect

class RestoredDesign(infrastructure.BrowserLogin):
    def setUp(self):
        super().setUp()
        self.page.wait_for_function("document.documentElement.dataset.design === 'restored-v1'")
    def test_themes_and_persistence(self):
        self.login()
        expect(self.page.locator('#a_mb')).to_have_value('500')
        self.assertEqual(self.page.locator('#th option').evaluate_all('(options)=>options.map(o=>o.value)'),['modern','nacht','bunt','werkstatt','galaxie'])
        for theme in ['modern','nacht','bunt','werkstatt','galaxie']:
            self.page.select_option('#th',theme)
            self.assertEqual(self.page.locator('html').get_attribute('data-theme'),theme)
        self.assertNotEqual(self.page.locator('body').evaluate('(e)=>getComputedStyle(e).backgroundImage'),'none')
        self.page.reload()
        self.page.wait_for_function("document.documentElement.dataset.theme === 'galaxie'")
        self.assertEqual(self.errors,[])
    def test_spool_and_fill_meter(self):
        self.page.route('**/api/filaments',lambda route:route.fulfill(content_type='application/json',body='[{"id":"abcd1234","brand":"Test","material":"PLA","color_name":"Rot","color_hex":"#ff0000","weight_total":1000,"weight_remaining":750}]'))
        self.login(); self.page.click('nav [data-t="fil"]')
        expect(self.page.locator('#ft .spool')).to_have_count(1)
        expect(self.page.locator('#ft .meter i')).to_have_attribute('style','width: 75%;')
        self.assertEqual(self.errors,[])
    def test_optional_preview_failure_keeps_session(self):
        self.page.route('**/api/list?**',lambda route:route.fulfill(content_type='application/json',body='{"path":"","items":[{"name":"fixture.stl","dir":false,"size":100,"mtime":1}]}'))
        self.page.route('https://cdn.jsdelivr.net/**',lambda route:route.abort())
        self.login(); expect(self.page.locator('#gr .open')).to_have_count(1)
        self.page.click('#gr .open')
        expect(self.page.locator('#viewer')).to_be_visible()
        expect(self.page.locator('#viewerInfo')).to_contain_text('Vorschau nicht verfügbar')
        self.page.click('#viewerClose')
        self.assertTrue(self.context.request.get(self.url+'/api/me').json()['auth'])
        self.assertTrue(self.page.is_visible('#app')); self.assertEqual(self.errors,[])

if __name__=='__main__': unittest.main()
