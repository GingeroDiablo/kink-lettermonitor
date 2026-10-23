"""Front-end regression tests for speculative secret KINK top-ten slots."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "docs" / "index.html"


class TopTenPlaceholderTests(unittest.TestCase):
    def test_reserved_rows_do_not_change_confirmed_codeword(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('id="secret-reserve"', html)
        self.assertIn('id="reserve-code"', html)
        self.assertIn('RESERVE_KEYS=["secret-top10-A","secret-top10-B"]', html)
        self.assertIn('function reserveSlots()', html)
        self.assertIn('function renderReserve()', html)
        self.assertIn("reserveSlots().forEach(function(k,i)", html)
        self.assertIn('RESERVE_KEYS.indexOf(k)!==-1', html)
        self.assertIn("tracks().filter(function(t){return t.rank>0})", html)

    @unittest.skipUnless(shutil.which("node"), "Node.js required to exercise frontend JS")
    def test_javascript_syntax_and_dynamic_slots(self):
        script = r'''
const assert=require("node:assert/strict");
const vm=require("node:vm");
const fs=require("node:fs");
const html=fs.readFileSync(process.argv[1],"utf8");
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(source,{filename:"docs/index.html"});
const start=source.indexOf("function tracks(){");
const end=source.indexOf("function evidence(");
assert.ok(start>=0 && end>start);
const state={
  tracks:[{rank:1232,title:"Wherever I May Roam"},{rank:34,title:"One"}],
  top10_unrevealed:[1,2,3,4,5,6,7,8,9,10]
};
const ctx={state,overrides:{"1232":"Q","secret-top10-A":"F"},
  $:()=>null,elt:()=>null,Option:()=>null,store:()=>{},update:()=>{}};
vm.createContext(ctx);
vm.runInContext(source.substring(start,end),ctx);
const slots=()=>Array.from(vm.runInContext("reserveSlots()",ctx));
assert.deepEqual(slots(),["secret-top10-A","secret-top10-B"]);
assert.equal(vm.runInContext("reserveLetter('secret-top10-A')",ctx),"F");
ctx.state.tracks.push({rank:7,title:"Secret Metallica"});
ctx.state.top10_unrevealed=[1,2,3,4,5,6,8,9,10];
assert.deepEqual(slots(),["secret-top10-A"]);
ctx.state.tracks.push({rank:3,title:"Another secret Metallica"});
assert.deepEqual(slots(),[]);
ctx.state.top10_unrevealed=[];
assert.deepEqual(slots(),[]);
assert.equal(ctx.overrides["secret-top10-A"],"F","Reserved letters stay saved for manual matching");
'''
        outcome = subprocess.run(
            ["node", "-e", script, str(HTML)], capture_output=True,
            text=True, timeout=20,
        )
        self.assertEqual(outcome.returncode, 0, outcome.stderr)


if __name__ == "__main__":
    unittest.main()
