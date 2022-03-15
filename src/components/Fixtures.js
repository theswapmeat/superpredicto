import React from "react";
import { useQuery } from "react-query";
import Fixture from "./Fixture";
import supabase from "../utils/supabase";
import { groupByKey } from "../utils/helpers";

const fetchFixtures = async (key, page) => {
  const res = await supabase
    .from("matches")
    .select("*, hometeamname:hometeamid(name), awayteamname:awayteamid(name)")
    .order("id", { ascending: true })
    .order("matchdate", { ascending: true });
  return res.data;
};

const Fixtures = () => {
  var picks = [];
  var groupedFixtures = [];

  const { data, status } = useQuery(["matches"], fetchFixtures);

  if (status === "success") {
    data.map((data) =>
      picks.push({
        id: data.id,
        matchdate: data.matchdate,
        hometeamscore: null,
        awayteamscore: null,
      })
    );
    console.log(data);
    var fixtures = groupByKey(data, "matchdate", { omitKey: true });

    for (const [key, value] of Object.entries(fixtures)) {
      groupedFixtures.push({ key, value });
    }
  }

  const handleUpdatePick = ({ id, hometeamscore, awayteamscore }) => {
    const objIndex = picks.findIndex((obj) => obj.id === id);
    picks[objIndex].hometeamscore = hometeamscore;
    picks[objIndex].awayteamscore = awayteamscore;
  };

  return (
    <div>
      <h2>Fixtures</h2>

      {status === "loading" && <p>Loading data</p>}

      {status === "error" && <p>Error fetching data</p>}

      {status === "success" && (
        <>
          <p>Success</p>
          <div>
            {groupedFixtures.map(
              (fixture) => (
                <Fixture
                  key={fixture.key}
                  date={fixture.key}
                  matches={fixture.value}
                  handleUpdatePick={handleUpdatePick}
                />
                // console.log(fixture)
              )
              // <Fixture
              //   key={fixture.id}
              //   fixture={fixture}
              //   handleUpdatePick={handleUpdatePick}
              // />
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default Fixtures;
