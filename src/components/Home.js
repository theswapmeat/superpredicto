import React, { useEffect, useState } from "react";
import supabase from "../utils/supabase";

function Home() {
  const [countries, setCountries] = useState();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);

    (async () => {
      const { data: country, error } = await supabase
        .from("countries")
        .select("*");
      setCountries(country);
      setLoading(false);
    })();
  }, []);

  return (
    <div>
      {loading ? (
        <h2>Loading...</h2>
      ) : (
        <h2>Loading complete</h2>
        // <pre>{JSON.stringify(countries, null, 2)}</pre>
      )}
    </div>
  );
}

export default Home;
