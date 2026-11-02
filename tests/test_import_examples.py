import ast,csv,io,json,re,unittest
from pathlib import Path

class ImportExamples(unittest.TestCase):
    def test_examples_match_actual_normalizer(self):
        source=ast.parse(Path('app/main.py').read_text('utf-8'))
        functions=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in {'norm','norm_price','norm_date'}]
        self.assertEqual(len(functions),3)
        namespace={'re':re}
        exec(compile(ast.Module(body=functions,type_ignores=[]),'import-normalizer','exec'),namespace)
        fields=next(ast.literal_eval(n.value) for n in source.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='FIELDS' for t in n.targets))
        json_rows=json.loads(Path('examples/filaments.example.json').read_text('utf-8-sig'))
        text=Path('examples/filaments.example.csv').read_text('utf-8-sig')
        delimiter=';' if text.split('\n',1)[0].count(';')>text.split('\n',1)[0].count(',') else ','
        reader=csv.DictReader(io.StringIO(text),delimiter=delimiter)
        self.assertEqual(reader.fieldnames,fields)
        csv_rows=list(reader)
        self.assertEqual(len(json_rows),2); self.assertEqual(len(csv_rows),2)
        normalize=namespace['norm']
        self.assertEqual([normalize(row) for row in json_rows],[normalize(row) for row in csv_rows])
        for row in json_rows:
            self.assertEqual(set(row),set(fields))
            self.assertRegex(row['color_hex'],r'^#[0-9A-Fa-f]{6}$')
            self.assertGreaterEqual(row['weight_remaining'],0)
            self.assertLessEqual(row['weight_remaining'],row['weight_total'])

if __name__=='__main__': unittest.main()
