# audit_peps.R
# Script to unnest Popolo candidate JSON records into flat R data frames & summary reports

library(jsonlite)
library(dplyr)
library(purrr)
library(tidyr)

audit_popolo_peps <- function(json_path = "popolo_sa_candidates.json") {
  if (!file.exists(json_path)) {
    stop(paste("Popolo output file not found:", json_path))
  }
  
  raw_data <- fromJSON(json_path, simplifyVector = FALSE)
  persons <- raw_data$persons
  
  df_parsed <- map_df(persons, function(p) {
    p_id <- p$id
    p_name <- p$name
    p_party <- if (!is.null(p$party_name)) p$party_name else NA_character_
    p_district <- if (!is.null(p$district)) p$district else NA_character_
    
    if (length(p$contact_details) == 0) {
      return(tibble(
        person_id = p_id,
        name = p_name,
        party = p_party,
        district = p_district,
        platform = NA_character_,
        profile_url = NA_character_,
        confidence = NA_real_,
        confidence_level = NA_character_,
        rationale = NA_character_,
        signals = NA_character_
      ))
    }
    
    map_df(p$contact_details, function(cd) {
      tibble(
        person_id = p_id,
        name = p_name,
        party = p_party,
        district = p_district,
        platform = cd$type,
        profile_url = cd$value,
        confidence = as.numeric(cd$confidence),
        confidence_level = cd$confidence_level,
        rationale = cd$rationale,
        signals = paste(cd$signals, collapse = " | ")
      )
    })
  })
  
  return(df_parsed)
}

if (!interactive()) {
  json_file <- "popolo_sa_candidates.json"
  if (file.exists(json_file)) {
    audit_df <- audit_popolo_peps(json_file)
    cat("\n=== PEP Social Accounts Audit Summary Table ===\n")
    print(as.data.frame(audit_df))
    
    # Save CSV report
    write.csv(audit_df, "pep_social_accounts_summary.csv", row.names = FALSE)
    cat("\nExported summary report to 'pep_social_accounts_summary.csv'.\n")
  } else {
    cat("Run 'python3 run_pipeline.py' first to generate JSON output.\n")
  }
}
