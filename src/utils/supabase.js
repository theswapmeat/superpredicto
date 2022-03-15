import { createClient } from "@supabase/supabase-js";

export default createClient(
  process.env.REACT_APP_URL,
  process.env.REACT_APP_API_KEY
);

