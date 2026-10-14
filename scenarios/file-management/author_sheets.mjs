import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const require = createRequire(process.env.FM_ARTIFACT_MODULE_ROOT + '/package.json');
const {Workbook, SpreadsheetFile} = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const output = process.argv[2];
for (const [i, variant] of ['a','b','c','d','e'].entries()) {
  const wb = Workbook.create(); const sheet = wb.worksheets.add('Expenses');
  sheet.getRange('A1:D1').values = [['Item','Category','Quantity','Unit cost']];
  sheet.getRange('A2:D4').values = [['Paper','Office',2+i,12],['Cable','Office',3+i,8],['Taxi','Travel',1+i,35]];
  sheet.getRange('E1').values = [['Amount']];
  sheet.getRange('E2:E4').formulas = [['=C2*D2'],['=C3*D3'],['=C4*D4']];
  sheet.getRange('D6').values = [['Total']]; sheet.getRange('E6').formulas = [['=SUM(E2:E4)']];
  sheet.getRange('A1:E6').format.font.name = 'Arial';
  sheet.getRange('A1:E1').format.fill = '#24465B';
  sheet.getRange('A1:E1').format.font.color = '#FFFFFF';
  sheet.getRange('A1:E1').format.font.bold = true;
  sheet.getRange('A1:E6').format.columnWidth = 17;
  sheet.getRange('A1:E6').format.rowHeight = 24;
  sheet.getRange('D2:E6').setNumberFormat('0.00');
  wb.recalculate();
  const values=sheet.getRange('E2:E4').values.map(r=>r[0]);
  const expected=[(2+i)*12,(3+i)*8,(1+i)*35];
  if (JSON.stringify(values)!==JSON.stringify(expected)) throw new Error('fixture formula mismatch');
  const png=await wb.render({sheetName:'Expenses',range:'A1:E6',scale:2});
  await fs.writeFile(`${output}/${variant}/ledger-preview.png`,new Uint8Array(await png.arrayBuffer()));
  await (await SpreadsheetFile.exportXlsx(wb)).save(`${output}/${variant}/ledger.xlsx`);
  console.log(JSON.stringify({variant,expected,total:sheet.getRange('E6').values[0][0]}));
}
