# process_pep_popolo.R
# Script to ingest Popolo JSON and render summary data frames & tables

library(jsonlite)
library(dplyr)
library(tidyr)
library(purrr)

process_popolo_peps <- function(json_path = "popolo_pep_output.json") {
  if (!file.exists(json_path)) {
    stop(paste("File not found:", json_path))
  }
  
  data <- fromJSON(json_path, simplifyVector = FALSE)
  persons <- data$persons
  
  parsed_rows <- map_df(persons, function(p) {
    p_id <- p$id
    p_name <- p$name
    
    if (length(p$contact_details) == 0) {
      return(tibble(
        person_id = p_id,
        name = p_name,
        platform = NA_character_,
        account_url = NA_character_,
        confidence = NA_real_,
        confidence_level = NA_character_,
        signals = NA_character_
      ))
    }
    
    map_df(p$contact_details, function(cd) {
      tibble(
        person_id = p_id,
        name = p_name,
        platform = cd$type,
        account_url = cd$value,
        confidence = as.numeric(cd$confidence),
        confidence_level = cd$confidence_level,
        signals = paste(cd$signals, collapse = " | ")
      )
    })
  })
  
  return(parsed_rows)
}

# Run processing if executed directly
if (!interactive()) {
  pep_table <- process_popolo_peps("popolo_pep_output.json")
  cat("=== Popolo PEP Social Profile Mapping Summary Table ===\n")
  print(as.data.frame(pep_table))
}
