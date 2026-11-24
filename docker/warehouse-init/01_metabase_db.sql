-- Runs once, when the warehouse volume is first created.
-- Metabase keeps its own settings (users, dashboards) in this separate database,
-- instead of its default H2 file, which is not meant for long-term use.
create database metabase;
