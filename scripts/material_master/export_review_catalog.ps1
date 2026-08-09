param(
    [string]$ReviewPath = "docs/archive/2026/reference/purchase-material-standardization.md",
    [string]$OutputDir = "data/material_purchase_2024"
)

$ErrorActionPreference = "Stop"

function Normalize-Cell([string]$value) {
    if ($null -eq $value) {
        return ""
    }
    return ($value -replace "<br\s*/?>", " " -replace "\s+", " ").Trim()
}

function Join-Unique([System.Collections.Generic.List[string]]$values) {
    return (($values | Where-Object { $_ } | Select-Object -Unique) -join " | ")
}

$rows = New-Object System.Collections.Generic.List[object]

foreach ($line in Get-Content -LiteralPath $ReviewPath -Encoding UTF8) {
    if ($line -notmatch '^\|\s*\d+\s*\|') {
        continue
    }

    $cols = $line -split '\|'
    if ($cols.Count -lt 10) {
        continue
    }

    $rows.Add([pscustomobject]@{
        sequence = [int](Normalize-Cell $cols[1])
        excel_row = [int](Normalize-Cell $cols[2])
        raw_name = Normalize-Cell $cols[3]
        standard_name = Normalize-Cell $cols[4]
        item_group = Normalize-Cell $cols[5]
        specs = Normalize-Cell $cols[6]
        unit = Normalize-Cell $cols[7]
        status = Normalize-Cell $cols[8]
        question = Normalize-Cell $cols[9]
    })
}

$catalogStatuses = @(
    "可建档",
    "可建档-低精度",
    "可建档-定制件",
    "可建档-加工件",
    "可合并",
    "可合并/单位待统一"
)

$catalogGroups = [ordered]@{}
$manualReview = New-Object System.Collections.Generic.List[object]
$serviceRows = New-Object System.Collections.Generic.List[object]

foreach ($row in $rows) {
    if ($catalogStatuses -contains $row.status) {
        $key = "$($row.standard_name)`u{241F}$($row.item_group)`u{241F}$($row.specs)`u{241F}$($row.unit)"
        if (-not $catalogGroups.Contains($key)) {
            $catalogGroups[$key] = [pscustomobject]@{
                standard_name = $row.standard_name
                item_group = $row.item_group
                specs = $row.specs
                unit = $row.unit
                source_count = 0
                raw_names = New-Object System.Collections.Generic.List[string]
                source_rows = New-Object System.Collections.Generic.List[string]
                statuses = New-Object System.Collections.Generic.List[string]
                notes = New-Object System.Collections.Generic.List[string]
            }
        }

        $group = $catalogGroups[$key]
        $group.source_count += 1
        $group.raw_names.Add($row.raw_name)
        $group.source_rows.Add("Sheet1:$($row.excel_row)")
        $group.statuses.Add($row.status)
        if ($row.question -and $row.question -ne "无") {
            $group.notes.Add($row.question)
        }
        continue
    }

    if ($row.status -match "服务|费用|非物料") {
        $serviceRows.Add($row)
    }
    else {
        $manualReview.Add($row)
    }
}

$catalog = New-Object System.Collections.Generic.List[object]
$aliases = New-Object System.Collections.Generic.List[object]
$index = 1

foreach ($entry in $catalogGroups.GetEnumerator()) {
    $item = $entry.Value
    $code = "REVIEW-MAT-{0:D5}" -f $index
    $aliasText = Join-Unique $item.raw_names
    $sourceText = Join-Unique $item.source_rows
    $statusText = Join-Unique $item.statuses
    $noteText = Join-Unique $item.notes

    $catalog.Add([pscustomobject]@{
        proposed_item_code = $code
        standard_name = $item.standard_name
        item_group = $item.item_group
        specs = $item.specs
        unit = $item.unit
        source_count = $item.source_count
        source_statuses = $statusText
        alias_names = $aliasText
        source_rows = $sourceText
        notes = $noteText
    })

    foreach ($alias in ($item.raw_names | Select-Object -Unique)) {
        $aliases.Add([pscustomobject]@{
            raw_name = $alias
            proposed_item_code = $code
            standard_name = $item.standard_name
            item_group = $item.item_group
            specs = $item.specs
            unit = $item.unit
        })
    }

    $index += 1
}

$manual = $manualReview | ForEach-Object {
    [pscustomobject]@{
        sequence = $_.sequence
        excel_row = $_.excel_row
        raw_name = $_.raw_name
        standard_name = $_.standard_name
        item_group = $_.item_group
        specs = $_.specs
        unit = $_.unit
        status = $_.status
        question = $_.question
    }
}

$services = $serviceRows | ForEach-Object {
    [pscustomobject]@{
        sequence = $_.sequence
        excel_row = $_.excel_row
        raw_name = $_.raw_name
        standard_name = $_.standard_name
        item_group = $_.item_group
        specs = $_.specs
        unit = $_.unit
        status = $_.status
        question = $_.question
    }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$catalogPath = Join-Path $OutputDir "standard_item_catalog_from_review.csv"
$aliasPath = Join-Path $OutputDir "item_aliases_from_review.csv"
$manualPath = Join-Path $OutputDir "manual_review_queue_from_review.csv"
$servicePath = Join-Path $OutputDir "non_stock_services_from_review.csv"

$catalog | Export-Csv -LiteralPath $catalogPath -NoTypeInformation -Encoding UTF8
$aliases | Export-Csv -LiteralPath $aliasPath -NoTypeInformation -Encoding UTF8
$manual | Export-Csv -LiteralPath $manualPath -NoTypeInformation -Encoding UTF8
$services | Export-Csv -LiteralPath $servicePath -NoTypeInformation -Encoding UTF8

[pscustomobject]@{
    review_rows = $rows.Count
    catalog_items = $catalog.Count
    alias_rows = $aliases.Count
    manual_review_rows = $manualReview.Count
    service_rows = $serviceRows.Count
    catalog_path = $catalogPath
    alias_path = $aliasPath
    manual_review_path = $manualPath
    service_path = $servicePath
} | ConvertTo-Json -Depth 3
