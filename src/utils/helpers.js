function groupByKey(list, key, { omitKey = false }) {
  console.log(list)
  return list.reduce(
    (hash, { [key]: value, ...rest }) => ({
      ...hash,
      [value]: (hash[value] || []).concat(
        omitKey ? { ...rest } : { [key]: value, ...rest }
      ),
    }),
    {}
  );
}

export { groupByKey };
