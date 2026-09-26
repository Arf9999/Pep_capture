/**
 * PEP Social Discovery - Google Sheet Auto-Formatter & Webhook
 * 
 * Instructions:
 * 1. In your Google Sheet, go to: Extensions > Apps Script
 * 2. Delete any existing code, paste this entire file, and click 'Save' (💾).
 * 3. Reload your Google Sheet in the browser.
 * 4. You will see a new menu at the top: '⚡ PEP Intelligence' -> click 'Apply Formatting & Color Rules'.
 * 5. (Optional) To allow the python script to sync directly, click:
 *    Deploy > New deployment > Web app (Who has access: Anyone) -> copy URL.
 */

// Adds a custom menu directly into your Google Sheets top menu bar
function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu("⚡ PEP Intelligence")
    .addItem("🎨 Apply Conditional Formatting Rules", "applyFormattingRules")
    .addItem("🧹 Purge EMAIL- Notes (Clean Sheet)", "cleanEmailFromNotes")
    .addItem("📊 Ensure 'notes' Column Exists", "ensureNotesColumn")
    .addToUi();
}

/**
 * Purges any stale 'EMAIL- ...' notes across all rows in the sheet.
 */
function cleanEmailFromNotes() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("persons");
  if (!sheet) {
    SpreadsheetApp.getUi().alert("Error: 'persons' worksheet not found!");
    return;
  }
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var notesCol = headers.indexOf("notes") + 1;
  if (notesCol === 0) return;

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  var range = sheet.getRange(2, notesCol, lastRow - 1, 1);
  var values = range.getValues();
  var backgrounds = range.getBackgrounds();
  var cleanedCount = 0;

  for (var i = 0; i < values.length; i++) {
    var val = values[i][0];
    if (val && typeof val === "string" && val.indexOf("EMAIL-") !== -1) {
      var parts = val.split(";").map(function(s) { return s.trim(); });
      var kept = parts.filter(function(p) { return p.indexOf("EMAIL-") !== 0; });
      var newVal = kept.join("; ");
      values[i][0] = newVal;
      if (!newVal) {
        backgrounds[i][0] = null;
      }
      cleanedCount++;
    }
  }

  if (cleanedCount > 0) {
    range.setValues(values);
    range.setBackgrounds(backgrounds);
  }
  SpreadsheetApp.getUi().alert("Done! Cleaned email notes from " + cleanedCount + " candidate rows.");
}

/**
 * Installs persistent Conditional Formatting rules across the sheet.
 */
function applyFormattingRules() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("persons");
  if (!sheet) {
    SpreadsheetApp.getUi().alert("Error: 'persons' worksheet not found!");
    return;
  }

  ensureNotesColumn();

  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var colMap = {};
  for (var c = 0; c < headers.length; c++) {
    colMap[headers[c]] = c + 1;
  }

  var numRows = Math.max(sheet.getLastRow() - 1, 5000);
  var rules = [];

  // 1. Final notes column formatting
  var notesCol = colMap["notes"];
  if (notesCol) {
    var notesRange = sheet.getRange(2, notesCol, numRows, 1);

    // Rule A: Probable / High Match (Green)
    var ruleGreen = SpreadsheetApp.newConditionalFormatRule()
      .whenTextContains("Probable")
      .setBackground("#B6D7A8") // Sage Green
      .setFontColor("#1c3b0d")
      .setRanges([notesRange])
      .build();

    // Rule B: Potential Match (Amber)
    var ruleAmber = SpreadsheetApp.newConditionalFormatRule()
      .whenTextContains("Potential")
      .setBackground("#FFE599") // Warm Amber
      .setFontColor("#7f6000")
      .setRanges([notesRange])
      .build();

    rules.push(ruleGreen);
    rules.push(ruleAmber);
  }

  // 2. Dropdown columns formatting: highlight "Auto_search" in soft cyan/blue
  var noteCols = ["note_fb", "note_ig", "note_tw", "note_tk", "note_yt", "note_li", "note_web"];
  var noteRanges = [];
  for (var i = 0; i < noteCols.length; i++) {
    var cIdx = colMap[noteCols[i]];
    if (cIdx) {
      noteRanges.push(sheet.getRange(2, cIdx, numRows, 1));
    }
  }

  if (noteRanges.length > 0) {
    var ruleAutoSearch = SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo("Auto_search")
      .setBackground("#D0E0FD") // Soft Google Blue
      .setFontColor("#174EA6")
      .setRanges(noteRanges)
      .build();
    rules.push(ruleAutoSearch);
  }

  sheet.setConditionalFormatRules(rules);
  SpreadsheetApp.getUi().alert("✅ Conditional formatting rules successfully installed on 'persons'!");
}

/**
 * Ensures the 'notes' column exists at the end of the sheet.
 */
function ensureNotesColumn() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("persons");
  if (!sheet) return;
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  if (headers.indexOf("notes") === -1) {
    var nextCol = sheet.getLastColumn() + 1;
    sheet.getRange(1, nextCol).setValue("notes");
    sheet.getRange(1, nextCol).setFontWeight("bold").setBackground("#f3f4f6");
  }
}

/**
 * Webhook receiver for live in-place syncing from Python
 */
function doPost(e) {
  if (!e || !e.postData || !e.postData.contents) {
    return ContentService.createTextOutput(JSON.stringify({status: "ok", message: "Webhook is alive and ready."}))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("persons");
  if (!sheet) {
    return ContentService.createTextOutput(JSON.stringify({error: "Worksheet 'persons' not found"}))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var data = JSON.parse(e.postData.contents);
  var updates = data.updates || [];

  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var colMap = {};
  for (var c = 0; c < headers.length; c++) colMap[headers[c]] = c + 1;

  if (!colMap["notes"]) {
    var nextCol = sheet.getLastColumn() + 1;
    sheet.getRange(1, nextCol).setValue("notes");
    colMap["notes"] = nextCol;
  }

  var idCol = colMap["id"];
  if (!idCol) {
    return ContentService.createTextOutput(JSON.stringify({error: "'id' column not found"}))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (data.action === "clean_email") {
    var notesColIdx = colMap["notes"];
    if (notesColIdx) {
      var lastRow = sheet.getLastRow();
      if (lastRow >= 2) {
        var nRange = sheet.getRange(2, notesColIdx, lastRow - 1, 1);
        var nVals = nRange.getValues();
        var nBgs = nRange.getBackgrounds();
        var cCount = 0;
        for (var n = 0; n < nVals.length; n++) {
          var nv = nVals[n][0];
          if (nv && typeof nv === "string" && nv.indexOf("EMAIL-") !== -1) {
            var nParts = nv.split(";").map(function(s) { return s.trim(); });
            var nKept = nParts.filter(function(p) { return p.indexOf("EMAIL-") !== 0; });
            var cleanStr = nKept.join("; ");
            nVals[n][0] = cleanStr;
            if (!cleanStr) nBgs[n][0] = null;
            cCount++;
          }
        }
        if (cCount > 0) {
          nRange.setValues(nVals);
          nRange.setBackgrounds(nBgs);
        }
        return ContentService.createTextOutput(JSON.stringify({status: "success", cleaned_rows: cCount}))
          .setMimeType(ContentService.MimeType.JSON);
      }
    }
    return ContentService.createTextOutput(JSON.stringify({status: "success", cleaned_rows: 0}))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var idRange = sheet.getRange(1, idCol, sheet.getLastRow(), 1);
  var updatedCount = 0;

  for (var i = 0; i < updates.length; i++) {
    var item = updates[i];
    if (!item.id) continue;

    var match = idRange.createTextFinder(item.id).matchEntireCell(true).findNext();
    if (!match) continue;
    var rowNum = match.getRow();

    for (var key in item) {
      if (key === "id" || key === "colors") continue;
      var cIdx = colMap[key];
      if (cIdx) {
        var cell = sheet.getRange(rowNum, cIdx);
        var curVal = cell.getValue();
        try {
          if (key === "notes") {
            // Strip any stale EMAIL- text from curVal
            var cleanCurVal = (curVal || "").toString().split(";").map(function(s) { return s.trim(); })
              .filter(function(p) { return p.indexOf("EMAIL-") !== 0; }).join("; ");
            
            if (!cleanCurVal) {
              cell.setValue(item[key]);
            } else if (item[key] && cleanCurVal.indexOf(item[key]) === -1) {
              cell.setValue(cleanCurVal + "; " + item[key]);
            } else {
              cell.setValue(cleanCurVal);
            }
            if (item.colors && item.colors["notes"]) {
              cell.setBackground(item.colors["notes"]);
            }
          } else if (!curVal || curVal.toString().trim() === "") {
            cell.setValue(item[key]);
            if (item.colors && item.colors[key]) {
              cell.setBackground(item.colors[key]);
            }
          }
        } catch (valErr) {
          if (item.colors && item.colors[key]) {
            cell.setBackground(item.colors[key]);
          }
        }
      }
    }
    updatedCount++;
  }

  return ContentService.createTextOutput(JSON.stringify({status: "success", updated: updatedCount}))
    .setMimeType(ContentService.MimeType.JSON);
}
